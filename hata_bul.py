import asyncio
import traceback

async def test_et():
    try:
        from tools.utils.native_ops import NativeOps
        print('Aşama 1: Dosyalar okunuyor...')
        print('Aşama 2: WhatsApp URL protokolü tetikleniyor...')
        await NativeOps.send_whatsapp_message('+905551234567', 'Test mesaji')
        print('BASARILI!')
    except Exception as e:
        print('\n' + '='*40)
        print('!!! ISTE ARAYUZUN GIZLEDIGI ASIL HATA !!!')
        print('='*40)
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(test_et())
