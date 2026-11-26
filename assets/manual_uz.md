# Drayver zaxiralovchi: qo'llanma

Windows'ni qayta o'rnatishdan oldin drayverlarni saqlab qo'ying, keyin ularni bir bosishda qayta o'rnating.

## Zaxiralash
1. Dastur ochilganda uchinchi tomon drayver paketlari ro'yxati o'qiladi (`pnputil /enum-drivers`).
   **Qurilmalar** ustunida drayver hozir qaysi qurilmada ishlatilayotgani ko'rsatiladi.
2. Qidiruv, sinf filtri va «Microsoft drayverlarini yashirish» bilan ro'yxatni toraytiring.
3. Keraklilarini belgilang, o'ng panelda zaxira papkasini tanlang (masalan flesh disk yoki D: disk).
4. **Zaxiralash** tugmasini bosing. Har bir drayver `Sinf\nomi_versiya` papkasiga eksport qilinadi
   va `drivers_manifest.json` fayli yaratiladi. Istasangiz oxirida ZIP arxiv ham yaratiladi.

## Tiklash
1. **Tiklash** bo'limida zaxira papkasini tanlang yoki oynaga sudrab tashlang.
2. Manifest bo'lsa, kompyuter nomi, sana va drayverlar ro'yxati ko'rsatiladi. Manifest bo'lmasa `.inf` fayllar qidiriladi.
3. Keraklilarini belgilab **O'rnatish** ni bosing (`pnputil /add-driver ... /subdirs /install`).
   Ba'zi drayverlar uchun kompyuterni qayta yuklash kerak bo'ladi.

## Administrator huquqi
Eksport va tiklash faqat administrator huquqida ishlaydi. Yuqori paneldagi
**Administrator sifatida ochish** tugmasi dasturni shu huquq bilan qayta ochadi.

## Buyruqlar
**Buyruqlarni ko'rsatish** bajariladigan `pnputil` buyruqlarini ko'rsatadi; ularni nusxalash
yoki `.bat` fayl qilib saqlash mumkin. **Jurnal** bo'limida har bir buyruq natijasi saqlanadi.
