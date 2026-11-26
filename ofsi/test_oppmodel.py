"""Tests de l'alignement d'identites et des etiquettes du modele d'adversaires (donnees synthetiques a verite connue)."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import numpy as np
import ofsi.rl2.oppmodel as O
ok = []
def check(n, c): ok.append(bool(c)); print(("PASS " if c else "FAIL ") + n)

def mkP(n_alive_ids, T_vals):
    """P[24,28] : joueur identifie k -> (log tuiles = 2+k, log troupes = 3+k) et type BOT (feat 8)."""
    P = np.zeros((24, 28), np.float32)
    for slot, k in enumerate(n_alive_ids): P[slot, 0] = 2 + k + T_vals; P[slot, 1] = 3 + k + T_vals; P[slot, 8] = 1.0
    return P
T = 40; death_at = 10; killed = 1                                  # le joueur d'identite 1 meurt au pas 10 (la liste se compacte)
P = np.zeros((T, 24, 28), np.float32); truth = np.full((T, 24), -1)
for t in range(T):
    alive = [0, 1, 2, 3] if t < death_at else [0, 2, 3]
    P[t] = mkP(alive, 0.001 * t); truth[t, :len(alive)] = alive
ep = np.zeros(T, np.int32); valid = np.abs(P).sum(2) > 0
ids = O.track_ids(P, valid, ep)
# les identites reconstruites doivent etre une bijection avec la verite (memes groupes), meme apres la compaction
mapping = {}
good = True
for t in range(T):
    for j in range(24):
        if truth[t, j] >= 0:
            k = int(ids[t, j]); good &= mapping.setdefault(int(truth[t, j]), k) == k
check("identites stables apres la mort d'un joueur au milieu de la liste", good)
check("le joueur 1 n'apparait plus apres sa mort", all(mapping[1] not in ids[t][valid[t]] for t in range(death_at, T)))
# etiquettes : elimination a h=5 pour les lignes dont le joueur 1 meurt dans les 5 pas
D = {"players": P.astype(np.float16), "self": np.zeros((T, 48), np.float16), "ep": ep, "step": np.arange(T)}
X, Yr, Ye, Mr, Me, e = O.build(D, max_rows=10**6, history=True)
# lignes concernees : pas t in [death_at-5, death_at-1] et identite = celle du joueur 1 (feat0 ~ 3 + t*0.001)
sel = [i for i in range(len(X)) if abs(X[i, 0] - (3 + 0.001 * np.round((X[i, 0] - 3) / 0.001))) < 1e-3 and abs(round(X[i, 0] - 3)) == 0 and Ye[i, 0, 0] == 1]
check("etiquette d'elimination a h=5 positive uniquement avant la mort", len(sel) == 5)
check("aucune elimination a h=5 pour les autres joueurs", Ye[:, 0, 0].sum() == 5)
check("regression masquee quand le joueur est mort", Mr[Ye[:, 0, 0] == 1, 0, 0].sum() == 0)
# AUC sur cas connus
y = np.array([0, 0, 1, 1]); check("AUC parfait = 1", O.auc(np.array([.1, .2, .8, .9]), y) == 1.0); check("AUC aleatoire = 0.5 (ex-aequo)", O.auc(np.array([.5, .5, .5, .5]), y) == 0.5)
print(f"{sum(ok)}/{len(ok)} PASS"); sys.exit(0 if all(ok) else 1)
