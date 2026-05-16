import re
import os
import sys
import json
import time
import base64
import requests
from urllib.parse import urljoin
from datetime import datetime

# ─────────────────────────────────────────────
# YAPILANDIRMA
# ─────────────────────────────────────────────
BASE_URL = "https://tv247.us/watch/"
OUTPUT_DIR = "playlist"  # Klasör adı
MAIN_PLAYLIST = "playlist.m3u"  # Ana playlist dosyası
CHANNELS_FILE = "channels.txt"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://tv247.us/",
}

# Bilinen kanal ID'leri (yeni kanallar otomatik eklenir)
CHANNEL_IDS = {
    "bein-sports-1-turkey": "62",
    "bein-sports-2-turkey": "63",
    "bein-sports-3-turkey": "64",
    "bein-sports-4-turkey": "67",
    "bein-sports-5-turkey": "1010",
    "trt-spor-turkey": "889",
    "a-spor-turkey": "1011",
    "now-tv-turkey": "1003",                           
    "atv-turkey": "1000",
    "arena-sport-1-premium": "134",
}

# Kanal logoları
LOGO_URLS = {
    "bein-sports-1-turkey": "https://static.epg.best/qa/beINSports1.qa.png",
    "bein-sports-2-turkey": "https://static.epg.best/qa/beINSports2.qa.png",
    "bein-sports-3-turkey": "https://static.epg.best/qa/beINSports3.qa.png",
    "bein-sports-4-turkey": "https://static.epg.best/qa/beINSports4.qa.png",
    "bein-sports-5-turkey": "https://static.epg.best/qa/beINSports5.qa.png",
    "atv-turkey": "https://i.postimg.cc/PxH8NQjN/Atv-logo-2010-svg.png",
    "now-tv-turkey": "https://i.postimg.cc/SKsCFTPD/nowtv.png",
    "a-spor-turkey": "https://upload.wikimedia.org/wikipedia/tr/e/e9/A_Spor_logosu.png",
    "trt-spor-turkey": "https://i.postimg.cc/5yyjxb2C/trt-spor.png",
    "arena-sport-1-premium": "https://upload.wikimedia.org/wikipedia/commons/e/ea/Logo_Arena_Sport_TV_1.png",
}

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


# ─────────────────────────────────────────────
# TOKEN OLUŞTUR
# ─────────────────────────────────────────────
def generate_playlist_url(channel_id):
    """Channel ID'den playlist URL'si oluştur"""
    ts = int(time.time() * 1000)
    
    token_data = {
        "channelId": str(channel_id),
        "ts": ts
    }
    
    token_json = json.dumps(token_data, separators=(',', ':'))
    token_b64 = base64.b64encode(token_json.encode()).decode()
    
    return f"https://chat.cfbu247.sbs/api/proxy/playlist?token={token_b64}"


# ─────────────────────────────────────────────
# KANAL ID BUL (Sayfadan)
# ─────────────────────────────────────────────
def find_channel_id_from_page(channel_slug):
    """
    Sayfa HTML'inden channel ID'yi çıkar
    """
    url = f"{BASE_URL}{channel_slug}/"
    session = requests.Session()
    session.headers.update(HEADERS)
    
    log(f"  Sayfa taranıyor: {url}")
    
    try:
        resp = session.get(url, timeout=30)
        html = resp.text
        
        # 1. Doğrudan sayfada ID ara
        id_patterns = [
            r'data-id=["\'](\d+)["\']',
            r'channel[_-]?id["\']?\s*[:=]\s*["\']?(\d+)',
            r'stream[_-]?id["\']?\s*[:=]\s*["\']?(\d+)',
            r'/embed/(\d+)',
            r'\?id=(\d+)',
            r'&id=(\d+)',
        ]
        
        for pattern in id_patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            if matches:
                channel_id = matches[0]
                log(f"  ✓ Sayfada ID bulundu: {channel_id}")
                return channel_id
        
        # 2. iframe src'lerini kontrol et
        iframe_pattern = r'<iframe[^>]+src=["\']([^"\']+)["\']'
        iframes = re.findall(iframe_pattern, html, re.IGNORECASE)
        
        for iframe_src in iframes:
            iframe_url = urljoin(url, iframe_src)
            log(f"  iframe kontrol: {iframe_url[:80]}...")
            
            # iframe URL'sinde ID var mı?
            id_match = re.search(r'[?&]id=(\d+)', iframe_url)
            if id_match:
                channel_id = id_match.group(1)
                log(f"  ✓ iframe URL'de ID bulundu: {channel_id}")
                return channel_id
            
            # iframe içeriğini çek
            try:
                resp2 = session.get(
                    iframe_url,
                    timeout=30,
                    headers={**HEADERS, "Referer": url}
                )
                iframe_html = resp2.text
                
                # iframe içinde ID ara
                for pattern in id_patterns:
                    matches = re.findall(pattern, iframe_html, re.IGNORECASE)
                    if matches:
                        channel_id = matches[0]
                        log(f"  ✓ iframe içinde ID bulundu: {channel_id}")
                        return channel_id
                
                # iframe içinde başka iframe var mı?
                inner_iframes = re.findall(iframe_pattern, iframe_html, re.IGNORECASE)
                for inner_src in inner_iframes:
                    inner_url = urljoin(iframe_url, inner_src)
                    log(f"    iç iframe: {inner_url[:80]}...")
                    
                    id_match = re.search(r'[?&]id=(\d+)', inner_url)
                    if id_match:
                        channel_id = id_match.group(1)
                        log(f"  ✓ iç iframe'de ID bulundu: {channel_id}")
                        return channel_id
                    
                    # İç iframe içeriğini çek
                    try:
                        resp3 = session.get(
                            inner_url,
                            timeout=30,
                            headers={**HEADERS, "Referer": iframe_url}
                        )
                        inner_html = resp3.text
                        
                        for pattern in id_patterns:
                            matches = re.findall(pattern, inner_html, re.IGNORECASE)
                            if matches:
                                channel_id = matches[0]
                                log(f"  ✓ iç iframe içinde ID bulundu: {channel_id}")
                                return channel_id
                        
                        # Token URL var mı?
                        token_match = re.search(
                            r'channelId["\']?\s*[:=]\s*["\']?(\d+)',
                            inner_html,
                            re.IGNORECASE
                        )
                        if token_match:
                            return token_match.group(1)
                            
                    except Exception as e:
                        log(f"    iç iframe hatası: {e}")
                        
            except Exception as e:
                log(f"  iframe hatası: {e}")
        
        # 3. Script tag'lerinde ara
        script_pattern = r'<script[^>]*>(.*?)</script>'
        scripts = re.findall(script_pattern, html, re.DOTALL | re.IGNORECASE)
        
        for script in scripts:
            for pattern in id_patterns:
                matches = re.findall(pattern, script, re.IGNORECASE)
                if matches:
                    channel_id = matches[0]
                    log(f"  ✓ Script'te ID bulundu: {channel_id}")
                    return channel_id
                    
    except Exception as e:
        log(f"  Sayfa hatası: {e}")
    
    return None


# ─────────────────────────────────────────────
# DOĞRUDAN TOKEN URL BUL
# ─────────────────────────────────────────────
def find_direct_token_url(channel_slug):
    """
    Sayfada hazır token URL'si ara
    """
    url = f"{BASE_URL}{channel_slug}/"
    session = requests.Session()
    session.headers.update(HEADERS)
    
    try:
        resp = session.get(url, timeout=30)
        html = resp.text
        
        # Hazır playlist URL'si var mı?
        token_pattern = r'(https?://[^\s"\'<>]+/api/proxy/playlist\?token=[A-Za-z0-9+/=_-]+)'
        
        # Ana sayfada ara
        matches = re.findall(token_pattern, html)
        if matches:
            log(f"  ✓ Doğrudan token URL bulundu!")
            return matches[0]
        
        # iframe'lerde ara
        iframe_pattern = r'<iframe[^>]+src=["\']([^"\']+)["\']'
        iframes = re.findall(iframe_pattern, html, re.IGNORECASE)
        
        for iframe_src in iframes:
            iframe_url = urljoin(url, iframe_src)
            
            try:
                resp2 = session.get(
                    iframe_url,
                    timeout=30,
                    headers={**HEADERS, "Referer": url}
                )
                
                matches = re.findall(token_pattern, resp2.text)
                if matches:
                    log(f"  ✓ iframe'de token URL bulundu!")
                    return matches[0]
                
                # Daha derin iframe
                inner_iframes = re.findall(iframe_pattern, resp2.text, re.IGNORECASE)
                for inner_src in inner_iframes:
                    inner_url = urljoin(iframe_url, inner_src)
                    
                    try:
                        resp3 = session.get(
                            inner_url,
                            timeout=30,
                            headers={**HEADERS, "Referer": iframe_url}
                        )
                        
                        matches = re.findall(token_pattern, resp3.text)
                        if matches:
                            log(f"  ✓ iç iframe'de token URL bulundu!")
                            return matches[0]
                            
                    except:
                        pass
                        
            except:
                pass
                
    except Exception as e:
        log(f"  Hata: {e}")
    
    return None


# ─────────────────────────────────────────────
# ANA STREAM BULMA FONKSİYONU
# ─────────────────────────────────────────────
def find_stream_url(channel_slug):
    """
    Kanal için stream URL'si bul
    """
    log(f"Kanal: {channel_slug}")
    
    # 1. Bilinen ID varsa doğrudan kullan
    if channel_slug in CHANNEL_IDS and CHANNEL_IDS[channel_slug]:
        channel_id = CHANNEL_IDS[channel_slug]
        log(f"  Bilinen ID: {channel_id}")
        return generate_playlist_url(channel_id)
    
    # 2. Doğrudan token URL ara
    log(f"  [1/3] Doğrudan token URL aranıyor...")
    direct_url = find_direct_token_url(channel_slug)
    if direct_url:
        return direct_url
    
    # 3. Sayfadan ID bul
    log(f"  [2/3] Sayfadan ID çıkarılıyor...")
    channel_id = find_channel_id_from_page(channel_slug)
    if channel_id:
        # Bulunan ID'yi kaydet
        CHANNEL_IDS[channel_slug] = channel_id
        return generate_playlist_url(channel_id)
    
    # 4. Slug'dan tahmin et (son çare)
    log(f"  [3/3] ID tahmin ediliyor...")
    
    # Bazı bilinen pattern'ler
    slug_guesses = {
        "atv": ["1", "101", "201"],
        "star-tv": ["2", "102", "202"],
        "show-tv": ["3", "103", "203"],
        "kanal-d": ["4", "104", "204"],
        "fox-tv": ["5", "105", "205"],
        "tv8": ["6", "106", "206"],
        "trt-1": ["10", "110", "210"],
    }
    
    for key, ids in slug_guesses.items():
        if key in channel_slug:
            for test_id in ids:
                log(f"    ID {test_id} deneniyor...")
                test_url = generate_playlist_url(test_id)
                
                # Test et
                try:
                    resp = requests.get(
                        test_url,
                        timeout=10,
                        headers=HEADERS
                    )
                    if resp.status_code == 200 and len(resp.content) > 100:
                        log(f"  ✓ Çalışan ID bulundu: {test_id}")
                        CHANNEL_IDS[channel_slug] = test_id
                        return test_url
                except:
                    pass
    
    log(f"  ✗ ID bulunamadı!")
    return None


# ─────────────────────────────────────────────
# KANAL LİSTESİ
# ─────────────────────────────────────────────
def load_channels():
    """channels.txt'den kanal listesi yükle"""
    channels = []
    
    if os.path.exists(CHANNELS_FILE):
        with open(CHANNELS_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split('|')
                slug = parts[0].strip()
                name = parts[1].strip() if len(parts) > 1 else slug.replace('-', ' ').title()
                channels.append({'slug': slug, 'name': name})
    else:
        # Örnek kanallar
        channels = [
            {'slug': 'bein-sports-1-turkey', 'name': 'beIN Sports 1'},
            {'slug': 'bein-sports-2-turkey', 'name': 'beIN Sports 2'},
            {'slug': 'bein-sports-3-turkey', 'name': 'beIN Sports 3'},
            {'slug': 'bein-sports-4-turkey', 'name': 'beIN Sports 4'},
            {'slug': 'bein-sports-5-turkey', 'name': 'beIN Sports 5'},
            {'slug': 'trt-spor-turkey', 'name': 'TRT Spor'},
            {'slug': 'a-spor-turkey', 'name': 'A Spor'},
            {'slug': 'now-tv-turkey', 'name': 'NOW TV'},
            {'slug': 'atv-turkey', 'name': 'ATV'},
            {'slug': 'arena-sport-1-premium', 'name': 'Arena Sport 1 Premium'},
        ]
    
    return channels


def generate_single_m3u(channel, output_dir):
    """Tek bir kanal için M3U dosyası oluştur"""
    # Dosya adını oluştur (geçersiz karakterleri temizle)
    safe_name = re.sub(r'[\\/*?:"<>|]', "", channel['name'])
    safe_name = safe_name.replace(' ', '_')
    filename = f"{safe_name}.m3u"
    filepath = os.path.join(output_dir, filename)
    
    # M3U içeriği
    lines = ['#EXTM3U']
    lines.append(f'# Updated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}')
    lines.append('')
    
    if channel.get('url'):
        # Logo URL'sini al
        logo_url = LOGO_URLS.get(channel['slug'], "")
        logo_param = f' tvg-logo="{logo_url}"' if logo_url else ""
        
        lines.append(
            f'#EXTINF:-1 tvg-id="{channel["slug"]}" '
            f'tvg-name="{channel["name"]}"{logo_param} '
            f'group-title="TV247",{channel["name"]}'
        )
        lines.append(channel['url'])
    else:
        lines.append(f'#EXTINF:-1 tvg-id="{channel["slug"]}" tvg-name="{channel["name"]}",{channel["name"]}')
        lines.append('# No stream URL found')
    
    content = '\n'.join(lines)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return filename, content


def generate_main_playlist(results, output_dir, main_playlist_name):
    """Ana playlist.m3u dosyasını oluştur (tüm kanalları içerir)"""
    lines = ['#EXTM3U']
    lines.append(f'# Updated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")}')
    lines.append('# This playlist contains all channels')
    lines.append('')
    
    for ch in results:
        if ch.get('url'):
            # Logo URL'sini al
            logo_url = LOGO_URLS.get(ch['slug'], "")
            logo_param = f' tvg-logo="{logo_url}"' if logo_url else ""
            
            lines.append(
                f'#EXTINF:-1 tvg-id="{ch["slug"]}" '
                f'tvg-name="{ch["name"]}"{logo_param} '
                f'group-title="TV247",{ch["name"]}'
            )
            lines.append(ch['url'])
            lines.append('')
    
    content = '\n'.join(lines)
    
    main_filepath = os.path.join(output_dir, main_playlist_name)
    with open(main_filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return content


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    log("=" * 50)
    log("TV247 M3U Generator - Playlist Klasörü")
    log("=" * 50)
    
    # Çıktı klasörünü oluştur
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        log(f"✓ '{OUTPUT_DIR}' klasörü oluşturuldu")
    else:
        log(f"✓ '{OUTPUT_DIR}' klasörü hazır")
    
    channels = load_channels()
    log(f"\n{len(channels)} kanal işlenecek\n")
    
    results = []
    created_files = []
    
    for i, ch in enumerate(channels):
        log(f"\n[{i+1}/{len(channels)}] {ch['name']}")
        log("-" * 40)
        
        stream_url = find_stream_url(ch['slug'])
        
        channel_data = {
            'slug': ch['slug'],
            'name': ch['name'],
            'url': stream_url
        }
        results.append(channel_data)
        
        # Tek kanal için M3U oluştur
        filename, content = generate_single_m3u(channel_data, OUTPUT_DIR)
        created_files.append(filename)
        
        if stream_url:
            log(f"✓ {filename} oluşturuldu")
            log(f"  URL: {stream_url[:80]}...")
        else:
            log(f"⚠ {filename} oluşturuldu (stream bulunamadı)")
        
        time.sleep(1)
    
    # Ana playlist.m3u dosyasını oluştur
    main_content = generate_main_playlist(results, OUTPUT_DIR, MAIN_PLAYLIST)
    log(f"\n✓ {MAIN_PLAYLIST} oluşturuldu (tüm kanalları içerir)")
    
    # Özet
    found = sum(1 for r in results if r.get('url'))
    log("\n" + "=" * 50)
    log(f"SONUÇ: {found}/{len(results)} kanal bulundu")
    log(f"✓ {len(created_files)} ayrı M3U dosyası '{OUTPUT_DIR}/' klasörüne kaydedildi")
    log(f"✓ Tüm kanallar '{OUTPUT_DIR}/{MAIN_PLAYLIST}' dosyasında birleştirildi")
    
    # Klasör içeriğini listele
    log(f"\n📁 '{OUTPUT_DIR}/' klasörü içeriği:")
    log(f"  📄 {MAIN_PLAYLIST} (ana playlist - tüm kanallar)")
    for filename in created_files[:10]:  # İlk 10'u göster
        log(f"  📺 {filename}")
    if len(created_files) > 10:
        log(f"  ... ve {len(created_files) - 10} dosya daha")
    
    # Bulunan ID'leri göster
    if CHANNEL_IDS:
        log("\n🔑 Bulunan Kanal ID'leri:")
        for slug, cid in list(CHANNEL_IDS.items())[:10]:
            if cid:
                log(f"  {slug}: {cid}")
        if len(CHANNEL_IDS) > 10:
            log(f"  ... ve {len(CHANNEL_IDS) - 10} ID daha")
    
    return 0 if found > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
