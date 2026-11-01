"""
Train the compact stroke-forecasting GRU that powers the "Rally" game.

Data: ShuttleSet22 (CoachAI Badminton Challenge @ IJCAI 2023, MIT licence)
      https://github.com/wywyWang/CoachAI-Projects
Task: given the last WINDOW shot types in a singles rally, predict the next shot type.

Outputs (written to --out):
  model.json   GRU weights + vocab + transition fallback, loaded by assets/rally.js
  metrics.json held-out accuracy of the GRU vs. baselines

Usage:
  python train_model.py --data "<path to Track 2: Stroke Forecasting/data>" --out ../assets/model
"""
import argparse, json, os, random
import numpy as np
import pandas as pd
import torch
import torch.nn as nn

WINDOW = 4
TYPES = ["short service", "long service", "net shot", "lob", "clear", "drop",
         "smash", "defensive shot", "drive", "push/rush"]
PAD = 0
TOK = {t: i + 1 for i, t in enumerate(TYPES)}  # 0 is padding
N_CLASSES = len(TYPES)


def load_rallies(data_dir):
    train = pd.read_csv(os.path.join(data_dir, "train.csv"))
    rallies_by_match = {}
    for (m, r), g in train.sort_values(["rally_id", "ball_round"]).groupby(["match_id", "rally_id"]):
        rallies_by_match.setdefault(m, []).append(g["type"].tolist())
    # val/test: stitch "given" + "gt" back together into full rallies
    held = []
    for split in ["val", "test"]:
        given = pd.read_csv(os.path.join(data_dir, f"{split}_given.csv"))[["rally_id", "ball_round", "type"]]
        gt = pd.read_csv(os.path.join(data_dir, f"{split}_gt.csv"))[["rally_id", "ball_round", "type"]]
        full = pd.concat([given, gt]).drop_duplicates(["rally_id", "ball_round"]).sort_values(["rally_id", "ball_round"])
        held += [g["type"].tolist() for _, g in full.groupby("rally_id")]
    return rallies_by_match, held


def to_samples(rallies):
    X, y = [], []
    for r in rallies:
        toks = [TOK[t] for t in r if t in TOK]
        for i in range(1, len(toks)):
            ctx = toks[max(0, i - WINDOW):i]
            X.append([PAD] * (WINDOW - len(ctx)) + ctx)
            y.append(toks[i] - 1)
    return np.array(X, dtype=np.int64), np.array(y, dtype=np.int64)


class StrokeGRU(nn.Module):
    def __init__(self, emb=16, hidden=32):
        super().__init__()
        self.emb = nn.Embedding(N_CLASSES + 1, emb, padding_idx=PAD)
        self.gru = nn.GRU(emb, hidden, batch_first=True)
        self.drop = nn.Dropout(0.2)
        self.out = nn.Linear(hidden, N_CLASSES)

    def forward(self, x):
        h, _ = self.gru(self.emb(x))
        return self.out(self.drop(h[:, -1]))


def topk_acc(logits, y, k):
    return (np.argsort(-logits, 1)[:, :k] == y[:, None]).any(1).mean()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", default="../assets/model")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    random.seed(a.seed); np.random.seed(a.seed); torch.manual_seed(a.seed)

    by_match, held = load_rallies(a.data)
    matches = sorted(by_match)
    random.shuffle(matches)
    n_val = max(1, len(matches) // 6)
    tr = [r for m in matches[n_val:] for r in by_match[m]]
    va = [r for m in matches[:n_val] for r in by_match[m]]
    Xtr, ytr = to_samples(tr); Xva, yva = to_samples(va); Xte, yte = to_samples(held)
    print(f"samples train={len(ytr)} val={len(yva)} test={len(yte)}")

    # ---- baselines (fit on train only) ----
    majority = np.bincount(ytr, minlength=N_CLASSES)
    bigram = np.ones((N_CLASSES + 1, N_CLASSES))  # Laplace smoothing; row = previous token
    for x, t in zip(Xtr, ytr):
        bigram[x[-1], t] += 1
    bigram /= bigram.sum(1, keepdims=True)

    # ---- GRU ----
    model = StrokeGRU()
    opt = torch.optim.AdamW(model.parameters(), lr=3e-3, weight_decay=1e-4)
    lossf = nn.CrossEntropyLoss()
    Xt, yt = torch.tensor(Xtr), torch.tensor(ytr)
    best, best_state, patience = 1e9, None, 0
    for ep in range(60):
        model.train()
        perm = torch.randperm(len(yt))
        for i in range(0, len(yt), 256):
            idx = perm[i:i + 256]
            opt.zero_grad(); l = lossf(model(Xt[idx]), yt[idx]); l.backward(); opt.step()
        model.eval()
        with torch.no_grad():
            vl = lossf(model(torch.tensor(Xva)), torch.tensor(yva)).item()
        if vl < best - 1e-4:
            best, best_state, patience = vl, {k: v.clone() for k, v in model.state_dict().items()}, 0
        else:
            patience += 1
            if patience >= 8:
                break
    model.load_state_dict(best_state); model.eval()
    print(f"stopped at epoch {ep}, best val loss {best:.4f}")

    with torch.no_grad():
        gru_logits = model(torch.tensor(Xte)).numpy()
    maj_logits = np.tile(majority, (len(yte), 1)).astype(float)
    bi_logits = bigram[Xte[:, -1]]
    metrics = {
        "dataset": "ShuttleSet22 (CoachAI Badminton Challenge, IJCAI 2023)",
        "test_rallies": len(held), "test_predictions": int(len(yte)),
        "train_predictions": int(len(ytr)), "window": WINDOW,
        "majority": {"top1": round(float(topk_acc(maj_logits, yte, 1)), 4), "top3": round(float(topk_acc(maj_logits, yte, 3)), 4)},
        "bigram": {"top1": round(float(topk_acc(bi_logits, yte, 1)), 4), "top3": round(float(topk_acc(bi_logits, yte, 3)), 4)},
        "gru": {"top1": round(float(topk_acc(gru_logits, yte, 1)), 4), "top3": round(float(topk_acc(gru_logits, yte, 3)), 4)},
    }
    print(json.dumps(metrics, indent=2))

    # ---- export: plain JSON so the browser needs no ML library ----
    sd = {k: v.numpy().round(5).tolist() for k, v in model.state_dict().items()}
    # Data-driven "legal reply" sets: shots that follow each shot at least 3% of the time in pro play
    counts = np.zeros((N_CLASSES, N_CLASSES))
    for r in tr:
        toks = [TOK[t] - 1 for t in r if t in TOK]
        for p, n in zip(toks, toks[1:]):
            counts[p, n] += 1
    replies = {TYPES[p]: [TYPES[n] for n in range(N_CLASSES)
                          if counts[p].sum() and counts[p, n] / counts[p].sum() >= 0.03]
               for p in range(N_CLASSES)}
    export = {
        "types": TYPES, "window": WINDOW, "hidden": 32, "emb": 16,
        "embedding": sd["emb.weight"],
        "W_ih": sd["gru.weight_ih_l0"], "W_hh": sd["gru.weight_hh_l0"],
        "b_ih": sd["gru.bias_ih_l0"], "b_hh": sd["gru.bias_hh_l0"],
        "W_out": sd["out.weight"], "b_out": sd["out.bias"],
        "bigram": bigram.round(5).tolist(),
        "replies": replies,
        "metrics": metrics,
        # parity fixtures so the JS forward pass can be checked against PyTorch
        "fixtures": [{"x": Xte[i].tolist(), "logits": gru_logits[i].round(4).tolist()} for i in range(0, 50, 5)],
    }
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "model.json"), "w") as f:
        json.dump(export, f, separators=(",", ":"))
    # Same data as a script tag, so the game also works when index.html is opened straight from disk.
    with open(os.path.join(a.out, "model.js"), "w") as f:
        f.write("window.RALLY_MODEL=" + json.dumps(export, separators=(",", ":")) + ";\n")
    with open(os.path.join(a.out, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)
    print("wrote", os.path.join(a.out, "model.json"))


if __name__ == "__main__":
    main()
