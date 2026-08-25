#!/bin/bash
# Buduje pakiet .deb dla File Managera (PyInstaller onedir + struktura /opt).
set -e
cd "$(dirname "$0")"

echo "=== File Manager - budowanie pakietu .deb ==="

VERSION=0.1.0
TAG=$(git describe --tags --abbrev=0 2>/dev/null || true)
if [[ "$TAG" =~ ^v([0-9]+\.[0-9]+\.[0-9]+)$ ]]; then
    VERSION=${TAG#v}
fi

PKG=packaging/debian
DIST=dist/file-manager

# 1. PyInstaller
if [ ! -d "$DIST" ]; then
    echo "==> PyInstaller: buduje binarie..."
    .venv/bin/python -m PyInstaller --noconfirm --clean file_manager.spec
fi

# 2. Struktura pakietu
echo "==> Skladam strukture pakietu..."
rm -rf "$PKG/opt" "$PKG/usr"
mkdir -p "$PKG/opt/file-manager" "$PKG/usr/bin" \
         "$PKG/usr/share/applications" "$PKG/usr/share/icons/hicolor/256x256/apps"

cp -r "$DIST"/* "$PKG/opt/file-manager/"
cp resources/icons/file_manager.png \
   "$PKG/usr/share/icons/hicolor/256x256/apps/file-manager.png"

cat > "$PKG/usr/bin/file-manager" << 'EOF'
#!/bin/bash
cd /opt/file-manager
exec ./file-manager "$@"
EOF
chmod 755 "$PKG/usr/bin/file-manager"

cat > "$PKG/usr/share/applications/file-manager.desktop" << EOF
[Desktop Entry]
Type=Application
Name=File Manager
Comment=Menedzer plikow: lokalne, FTP/SFTP, NAS, chmury
Exec=/usr/bin/file-manager
Icon=file-manager
Terminal=false
Categories=Utility;FileTools;FileManager;
Keywords=files;ftp;sftp;smb;nas;cloud;
EOF

# 3. Wersja w control
sed -i "s/^Version:.*/Version: $VERSION/" "$PKG/DEBIAN/control"

# 4. Budowa .deb
echo "==> dpkg-deb..."
dpkg-deb --root-owner-group --build "$PKG" "file-manager_${VERSION}_amd64.deb"

echo ""
echo "=== GOTOWE: file-manager_${VERSION}_amd64.deb ==="
echo "Instalacja:   sudo dpkg -i file-manager_${VERSION}_amd64.deb"
echo "Uruchomienie: file-manager  (albo z menu aplikacji)"
echo "Usuwanie:     sudo apt remove file-manager"
