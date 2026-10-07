# Interaktiv animierte Scheibe – Rennrad

## Lokal starten
Nicht per Doppelklick (file://) öffnen, sondern über einen lokalen Server:
- VS Code: Erweiterung "Live Server" → Rechtsklick auf index.html → "Open with Live Server"
- oder Terminal im Projektordner: `python3 -m http.server 8000` → http://localhost:8000

## Bildmaterial neu erzeugen
`pip install pillow numpy scipy`, dann `python3 tools/generate_assets.py`
(Quellen: img/quelle/Vorderrad.png, img/quelle/Hinterrad.png).
Nur Rahmen und bike-layout.css neu: `python3 tools/generate_assets.py --nur-rahmen`

## Deployment
Den kompletten Ordner (index.html, style.css, bike-layout.css, app.js, img/, tools/) hochladen.
Dateinamen sind auf Linux-Servern case-sensitiv.
