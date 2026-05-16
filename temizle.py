import chromadb

paths = [
    r"C:\Users\proog\OneDrive\Masaüstü\Projeler\My_Jarvis_Project\jarvis_memory_db",
    r"C:\Users\proog\OneDrive\Masaüstü\Projeler\My_Jarvis_Project\memory_db",
]

KIRLI_TAGLAR = [
    "[ne yaptim]", "[ne işe yaradi]",
    "[ne başarisiz]", "[sonraki seferde]"
]

for path in paths:
    print(f"\n--- {path} ---")
    try:
        client = chromadb.PersistentClient(path=path)
        collections = client.list_collections()
        print(f"Koleksiyonlar: {[c.name for c in collections]}")
        
        for col_info in collections:
            col = client.get_collection(col_info.name)
            results = col.get(include=["documents"])
            docs = results.get("documents", [])
            ids = results.get("ids", [])
            
            bad_ids = []
            for i, doc in enumerate(docs):
                if doc and any(tag in doc.lower() for tag in KIRLI_TAGLAR):
                    bad_ids.append(ids[i])
                    print(f"  Kirli: {doc[:80]}")
            
            if bad_ids:
                col.delete(ids=bad_ids)
                print(f"  {len(bad_ids)} kayıt silindi.")
            else:
                print(f"  Temiz, silinecek kayıt yok.")
    except Exception as e:
        print(f"Hata: {e}")