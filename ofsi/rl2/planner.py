"""Planification par recherche sur SNAPSHOTS EXACTS du moteur (MISSION §25).
A certains pas de decision : snapshot -> pour chaque action candidate (celle du professeur + alternatives LEGALES de counterfactual.alternatives) -> restauration, simulation de
H decisions (action candidate puis professeur de rollout) -> score = progression vers la victoire reelle (victoire +3, mort -1). On ne s'ecarte du professeur que si le gain mesure depasse
`margin` (limite la malediction du vainqueur : un max sur des evaluations bruitees est biaise vers le haut). Le moteur et l'etat Python sont restaures EXACTEMENT apres la recherche."""
import sys, json, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from ofsi.rl2.counterfactual import alternatives, play_from
from ofsi.rl2.teacher_v2 import TeacherV2


class PlannerAbort(RuntimeError):
    """Une restauration a echoue APRES le debut de la recherche : le moteur est dans un etat divergent (le runner n'est remplace qu'en cas de succes). La partie doit etre abandonnee, jamais poursuivie."""


def score(res):
    prog, alive, win, _ = res
    return 3.0 if win else (-1.0 if not alive else prog)


class Planner:
    def __init__(self, params=None, H=30, every=4, margin=0.05, rollout_seed=1000, keep=None):
        self.params, self.H, self.every, self.margin, self.rs, self.keep = params or {}, H, every, margin, rollout_seed, keep
        self.n_plans = 0; self.n_switch = 0; self.n_snap_invalid = 0; self.chosen = {}; self.gains = []

    def choose(self, sess, obs, base_acts, step):
        st, costs, cands = sess.cur
        if st.get("spawnPhase") or step % self.every != 0: return base_acts
        saved = (sess.step_i, dict(sess.cache), sess.grid_at, sess.last, sess.cur, sess.invalid_exec, sess.exec_n)
        snap = sess.e.snapshot()
        try: sess.e.restore(snap)                      # VALIDATION : le snapshot doit etre restaurable ; une restauration immediate ne change pas l'etat (verifie par test) ; en cas d'echec le runner d'origine est conserve
        except Exception: self.n_snap_invalid += 1; return base_acts            # snapshot invalide (limite du moteur au commit epingle) : on ne planifie pas ce pas
        options = {"teacher": base_acts}; options.update(alternatives(obs, st, cands))
        if self.keep: options = {k: v for k, v in options.items() if k == "teacher" or k in self.keep}
        scores = {}
        try:
            for name, acts in options.items():
                sess.e.restore(snap); scores[name] = score(play_from(sess, acts, TeacherV2(seed=self.rs, **self.params), self.H))
            sess.e.restore(snap)
        except Exception as e: raise PlannerAbort(str(e)[:200])
        sess.step_i, sess.cache, sess.grid_at, sess.last, sess.cur, sess.invalid_exec, sess.exec_n = saved       # etat identique a l'entree
        best = max(scores, key=scores.get); self.n_plans += 1
        if best != "teacher" and scores[best] - scores["teacher"] > self.margin:
            self.n_switch += 1; self.chosen[best] = self.chosen.get(best, 0) + 1; self.gains.append(scores[best] - scores["teacher"]); return options[best]
        return base_acts
