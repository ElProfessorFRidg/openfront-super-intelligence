"""Profil d'une boucle de decision v2 : temps moteur (IPC) vs Python (obs, masques, professeur). Mesure reelle, une session."""
import sys, time, collections, cProfile, pstats, io, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from ofsi.rl2.env2 import Session
from ofsi.rl2.teacher_v2 import TeacherV2
from ofsi.client import OFEnvProc
T = collections.defaultdict(float); N = collections.defaultdict(int)
orig = OFEnvProc.call
def timed(self, cmd, **kw):
    t = time.perf_counter(); r = orig(self, cmd, **kw); T[cmd] += time.perf_counter() - t; N[cmd] += 1; return r
OFEnvProc.call = timed
s = Session(); o = s.start({"map": "Onion", "bots": 8, "difficulty": "Easy"}, "prof0001x"); te = TeacherV2(seed=0)
pr = cProfile.Profile(); n = 0; t0 = time.perf_counter(); pr.enable()
while n < 300:
    if o is None: break
    st, costs, cands = s.cur; A = te.act(o, st, costs, cands); r = s.apply(A)
    if st.get("spawnPhase"): o = s.spawn_wait()
    else: o = s.observe()
    n += 1
    if r.get("winner") is not None: break
pr.disable(); tot = time.perf_counter() - t0
print(f"{n} decisions en {tot:.1f}s = {n/tot:.1f} dec/s (1 session, CPU partage)")
eng = sum(T.values()); print(f"temps en appels moteur (IPC+moteur): {eng:.1f}s ({eng/tot*100:.0f} %) ; Python (obs/masques/prof): {tot-eng:.1f}s ({(tot-eng)/tot*100:.0f} %)")
for k, v in sorted(T.items(), key=lambda x: -x[1]): print(f"  {k:16s} {N[k]:5d} appels  {v:6.2f}s  {v/N[k]*1000:7.1f} ms/appel")
sio = io.StringIO(); pstats.Stats(pr, stream=sio).sort_stats("cumulative").print_stats(12); print("\n".join(l for l in sio.getvalue().splitlines() if "ofsi" in l or "numpy" in l)[:1800])
s.close()
