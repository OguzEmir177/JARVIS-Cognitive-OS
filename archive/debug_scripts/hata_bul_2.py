import asyncio
import traceback
import inspect

async def test_et():
    try:
        print('Asama 1: WhatsAppTool ice aktariliyor...')
        from tools.system_tool import WhatsAppTool
        tool = WhatsAppTool()
        
        print('Asama 2: Aractan Ablam kisisi aranip mesaj tetikleniyor...')
        sonuc = tool.execute(arg='Ablam|Bu bir izolasyon testidir', context={})
        if inspect.iscoroutine(sonuc):
            sonuc = await sonuc
            
        print('\nIslem bitti! ToolResult ciktisi:')
        try:
            print(sonuc.to_dict())
        except:
            print(sonuc)
            
    except Exception as e:
        print('\n' + '='*40)
        print('!!! ISTE GIZLENEN ASIL HATA !!!')
        print('='*40)
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(test_et())
