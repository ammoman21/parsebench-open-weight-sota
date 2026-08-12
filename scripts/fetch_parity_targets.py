import json, urllib.request, sys
API="https://api.github.com/repos/HuanzhiMao/BFCL-Result/contents/2025-12-16/score/{m}/{g}"
RAW="https://raw.githubusercontent.com/HuanzhiMao/BFCL-Result/main/2025-12-16/score/{m}/{g}/{f}"
def get(u):
    return urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"x"})).read()
for model in ["qwen3-14b-FC","Qwen_Qwen3-8B-FC"]:
    print(f"\n########## {model} ##########")
    for grp in ["non_live","live","multi_turn","agentic"]:
        try: items=json.loads(get(API.format(m=model,g=grp)))
        except Exception as e: print(f"  [{grp}] unavailable: {e}"); continue
        for it in items:
            f=it["name"]
            if not f.endswith("_score.json"): continue
            try:
                first=get(RAW.format(m=model,g=grp,f=f)).split(b"\n")[0]
                acc=json.loads(first).get("accuracy")
                cat=f.replace("BFCL_v4_","").replace("_score.json","")
                print(f"  {grp:11s} {cat:28s} {acc:.4f}")
            except Exception as e:
                print(f"  {grp:11s} {f:28s} ERR {e}")
