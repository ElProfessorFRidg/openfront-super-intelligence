"""Reseau v2 : encodeur a jetons d'entites (joueurs, unites, attaques) + vue geographique convolutive -> transformer -> tete de valeur et decodeur
d'actions autoregressif (type -> pointeur vers un candidat legal -> parametre), jusqu'a M_SUB actions par decision. Masques exacts appliques partout."""
import torch
import torch.nn as nn
import torch.nn.functional as F
from ofsi.rl2 import space as S

NEG = -1e9


class PolicyV2(nn.Module):
    def __init__(self, d=128, layers=4, heads=4, ff=512):
        super().__init__()
        self.d = d
        mlp = lambda i: nn.Sequential(nn.Linear(i, d), nn.GELU(), nn.Linear(d, d))
        self.e_self, self.e_pl, self.e_un, self.e_at = mlp(S.S_DIM), mlp(S.FP), mlp(S.FU), mlp(S.FA)
        self.kind = nn.Embedding(5, d)                                  # self / joueur / unite / attaque / grille
        self.slot_pl, self.slot_un, self.slot_at = nn.Embedding(S.N_PLAYERS, d), nn.Embedding(S.N_UNITS, d), nn.Embedding(S.N_ATT, d)
        self.conv = nn.Sequential(nn.Conv2d(4, 32, 3, padding=1), nn.GELU(), nn.Conv2d(32, 64, 3, stride=2, padding=1), nn.GELU(), nn.Conv2d(64, d, 3, stride=2, padding=1))   # 32 -> 8x8
        self.slot_g = nn.Embedding(64, d)
        layer = nn.TransformerEncoderLayer(d, heads, ff, batch_first=True, norm_first=True, dropout=0.0)
        self.enc = nn.TransformerEncoder(layer, layers, enable_nested_tensor=False)
        self.out_norm = nn.LayerNorm(d)
        self.value = nn.Sequential(nn.Linear(d, d), nn.GELU(), nn.Linear(d, 1))
        # --- decodeur d'actions ---
        self.type_emb = nn.Embedding(S.NT, d)
        self.q_in = nn.Linear(d, d)
        self.type_head = nn.Sequential(nn.Linear(d, d), nn.GELU(), nn.Linear(d, S.NT))
        self.bank_emb = nn.ModuleList([nn.Sequential(nn.Linear(S.FC, d), nn.GELU(), nn.Linear(d, d)) for _ in S.DOM])
        self.register_buffer("dom_id", torch.as_tensor(S.DOM_ID))
        self.dom_emb = nn.Embedding(len(S.DOM), d)
        self.ptr_q, self.ptr_k = nn.Linear(d, d), nn.Linear(d, d)
        self.param_head = nn.Sequential(nn.Linear(2 * d, d), nn.GELU(), nn.Linear(d, len(S.FRACS)))
        self.register_buffer("uses_param", torch.as_tensor(S.USES_PARAM))
        no_ptr = torch.zeros(S.NT, dtype=torch.bool); no_ptr[list(S.NO_PTR)] = True
        self.register_buffer("no_ptr", no_ptr)

    # ---------- encodage ----------
    def encode(self, o):
        B = o["self"].shape[0]; dev = o["self"].device
        tok_s = self.e_self(o["self"]).unsqueeze(1) + self.kind.weight[0]
        tok_p = self.e_pl(o["players"]) + self.kind.weight[1] + self.slot_pl.weight
        tok_u = self.e_un(o["units"]) + self.kind.weight[2] + self.slot_un.weight
        tok_a = self.e_at(o["atts"]) + self.kind.weight[3] + self.slot_at.weight
        g = self.conv(o["grid"]).flatten(2).transpose(1, 2) + self.kind.weight[4] + self.slot_g.weight          # [B,64,d]
        x = torch.cat([tok_s, tok_p, tok_u, tok_a, g], 1)
        valid = torch.cat([torch.ones(B, 1, dtype=torch.bool, device=dev), o["pmask"], o["umask"], o["amask"], torch.ones(B, 64, dtype=torch.bool, device=dev)], 1)
        h = self.enc(x, src_key_padding_mask=~valid)
        h = self.out_norm(h)
        ctx = h[:, 0]
        bank = torch.stack([self.bank_emb[i](o["bank"][:, o_:o_ + sz]) for i, (n, sz) in enumerate(S.DOM) for o_ in [S.OFF[n][0]]], 0) if False else None
        parts = []
        for i, (n, sz) in enumerate(S.DOM):
            a = S.OFF[n][0]; parts.append(self.bank_emb[i](o["bank"][:, a:a + sz]))
        bank = torch.cat(parts, 1) + self.dom_emb(self.dom_id)                                                # [B,NB,d]
        return ctx, bank, h

    def value_of(self, o):
        ctx, _, _ = self.encode(o)
        return self.value(ctx).squeeze(-1).float()

    # ---------- decodage autoregressif ----------
    def act(self, o, actions=None, greedy=False):
        """o : dict de tenseurs (batch). actions=None -> echantillonne ; sinon teacher forcing sur (types, ptrs, params) [B,M].
        Retourne dict : types, ptrs, params [B,M], logp [B] (somme), entropy [B], value [B]."""
        ctx, bank, _ = self.encode(o)
        B, M = ctx.shape[0], S.M_SUB; dev = ctx.device
        used = torch.zeros(B, S.NT, dtype=torch.bool, device=dev); alive = torch.ones(B, dtype=torch.bool, device=dev)
        prev = torch.zeros(B, self.d, device=dev, dtype=ctx.dtype)
        bank_k = self.ptr_k(bank)                                                                             # [B,NB,d]
        types, ptrs, params = [], [], []; logp = torch.zeros(B, device=dev); ent = torch.zeros(B, device=dev)
        for k in range(M):
            q = self.q_in(ctx + prev)
            tl = self.type_head(q).float()
            m = o["type_mask"] & ~used
            m[:, S.T["STOP"]] = m[:, S.T["STOP"]] | (o["type_mask"][:, S.T["STOP"]])
            tl = tl.masked_fill(~m, NEG)
            if actions is None:
                dist = torch.distributions.Categorical(logits=tl); t = tl.argmax(-1) if greedy else dist.sample()
            else:
                t = actions["types"][:, k]; dist = torch.distributions.Categorical(logits=tl)
            t = torch.where(alive, t, torch.full_like(t, S.T["STOP"]))
            lp = dist.log_prob(t); en = dist.entropy()
            temb = self.type_emb(t)
            # pointeur
            has_ptr = alive & ~self.no_ptr[t]
            qq = self.ptr_q(q + temb).unsqueeze(1)                                                            # [B,1,d]
            sc = (qq * bank_k).sum(-1).float() / (self.d ** 0.5)                                              # [B,NB]
            pm = o["ptr_mask"][torch.arange(B, device=dev), t]                                                # [B,NB]
            sc = sc.masked_fill(~pm, NEG); pm_any = pm.any(-1)
            sc = torch.where(pm_any.unsqueeze(-1), sc, torch.zeros_like(sc))                                  # evite NaN si aucun candidat
            pd = torch.distributions.Categorical(logits=sc)
            if actions is None: p = sc.argmax(-1) if greedy else pd.sample()
            else: p = actions["ptrs"][:, k]
            p = torch.where(has_ptr, p, torch.zeros_like(p))        # sans pointeur : indice 0 FORCE avant tout usage (sinon echantillonnage != reevaluation)
            lpp = pd.log_prob(p); enp = pd.entropy()
            sel = bank[torch.arange(B, device=dev), p]
            par_l = self.param_head(torch.cat([q + temb, sel], -1)).float(); prd = torch.distributions.Categorical(logits=par_l)
            if actions is None: pr = par_l.argmax(-1) if greedy else prd.sample()
            else: pr = actions["params"][:, k]
            lpr = prd.log_prob(pr); enr = prd.entropy(); has_par = alive & self.uses_param[t]
            logp = logp + torch.where(alive, lp, 0 * lp) + torch.where(has_ptr, lpp, 0 * lpp) + torch.where(has_par, lpr, 0 * lpr)
            ent = ent + torch.where(alive, en, 0 * en) + torch.where(has_ptr, enp, 0 * enp) + torch.where(has_par, enr, 0 * enr)
            types.append(t); ptrs.append(p); params.append(torch.where(has_par, pr, torch.zeros_like(pr)))
            used = used | F.one_hot(t, S.NT).bool(); used[:, S.T["STOP"]] = False
            prev = prev + temb * alive.unsqueeze(-1)
            alive = alive & (t != S.T["STOP"])
        return {"types": torch.stack(types, 1), "ptrs": torch.stack(ptrs, 1), "params": torch.stack(params, 1), "logp": logp, "entropy": ent, "value": self.value(ctx).squeeze(-1).float()}


def collate(obs_list, device):
    """Liste de dicts numpy -> dict de tenseurs sur `device`."""
    import numpy as np
    out = {}
    for k in obs_list[0]:
        arr = np.stack([o[k] for o in obs_list]); t = torch.from_numpy(arr)
        out[k] = t.to(device, non_blocking=True)
    return out
