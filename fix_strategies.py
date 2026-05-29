import json

f = open('memory_db/learned_strategies.json', 'r', encoding='utf-8')
d = json.load(f)
f.close()

# Delete incorrect strategies on the calculator
to_delete = [k for k in d if 'hesap' in k.lower()]
for k in to_delete:
    chain = d[k]["tool_chain"]
    print(f"SILINIYOR: {k} -> {chain}")
    del d[k]

f = open('memory_db/learned_strategies.json', 'w', encoding='utf-8')
json.dump(d, f, indent=2, ensure_ascii=False)
f.close()
print(f"\n{len(to_delete)} incorrect strategy deleted.")
