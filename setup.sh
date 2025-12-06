#!/bin/bash

echo "=========================================="
echo "  Calendar Aggregator - Kurulum Scripti  "
echo "=========================================="
echo ""

ENV_FILE=".env"

if [ -f "$ENV_FILE" ]; then
    echo "[!] .env dosyasi zaten mevcut."
    read -p "Uzerine yazmak ister misiniz? (e/h): " overwrite
    if [ "$overwrite" != "e" ] && [ "$overwrite" != "E" ]; then
        echo "Mevcut .env dosyasi korunuyor."
        echo ""
    else
        rm "$ENV_FILE"
    fi
fi

if [ ! -f "$ENV_FILE" ]; then
    echo "[*] Guvenli SESSION_SECRET olusturuluyor..."
    SESSION_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || openssl rand -hex 32)
    
    echo "[*] Admin bilgilerini giriniz..."
    read -p "Admin kullanici adi [admin]: " ADMIN_USER
    ADMIN_USER=${ADMIN_USER:-admin}
    
    while true; do
        read -sp "Admin sifresi [en az 8 karakter]: " ADMIN_PASS
        echo ""
        if [ ${#ADMIN_PASS} -ge 8 ]; then
            break
        fi
        echo "[!] Sifre en az 8 karakter olmalidir."
    done
    
    read -p "Sunucu portu [5000]: " PORT
    PORT=${PORT:-5000}
    
    cat > "$ENV_FILE" << EOF
# Calendar Aggregator Yapilandirmasi
# Bu dosya setup.sh tarafindan olusturuldu

# KRITIK: Bu anahtari degistirmeyin, tum oturumlar kapanir
SESSION_SECRET=$SESSION_SECRET

# Admin hesabi (ilk giris icin)
ADMIN_USERNAME=$ADMIN_USER
ADMIN_PASSWORD=$ADMIN_PASS

# Sunucu ayarlari
HOST=0.0.0.0
PORT=$PORT
EOF

    echo ""
    echo "[+] .env dosyasi olusturuldu!"
fi

echo ""
echo "[*] Python bagimliliklar kontrol ediliyor..."

if ! command -v python3 &> /dev/null; then
    echo "[!] Python3 bulunamadi. Lutfen yukleyin."
    exit 1
fi

if [ ! -d "venv" ]; then
    echo "[*] Virtual environment olusturuluyor..."
    python3 -m venv venv
fi

echo "[*] Virtual environment aktif ediliyor..."
source venv/bin/activate

echo "[*] Bagimliliklari yukluyor..."
pip install -q -r requirements.txt

echo ""
echo "=========================================="
echo "  Kurulum Tamamlandi!                    "
echo "=========================================="
echo ""
echo "Uygulamayi baslatmak icin:"
echo ""
echo "  source venv/bin/activate"
echo "  python main.py"
echo ""
echo "Veya production icin:"
echo ""
echo "  source venv/bin/activate"
echo "  pip install gunicorn"
echo "  gunicorn -w 4 -b 0.0.0.0:5000 main:app -k uvicorn.workers.UvicornWorker"
echo ""
echo "Tarayicinizda: http://localhost:$PORT"
echo ""
