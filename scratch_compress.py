import PIL.Image
import os

img = PIL.Image.open(r'C:\Users\genta\.gemini\antigravity\brain\25ab8214-db12-46b5-a087-6cb1562f0fc1\rich_menu_yonaguni_v4_1776603175171.png')
img = img.resize((2500, 1686), PIL.Image.Resampling.LANCZOS)
if img.mode in ('RGBA', 'P'): img = img.convert('RGB')
img.save(r'C:\Users\genta\Ecojima-Bot\rich_menu_final_v4.jpg', 'JPEG', quality=70, optimize=True)
size_kb = os.path.getsize(r"C:\Users\genta\Ecojima-Bot\rich_menu_final_v4.jpg") / 1024
print(f'Done. Size: {size_kb:.2f} KB')
