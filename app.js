/**
 * Interaktiv animierte Scheibe – Variante Rennrad
 * - Zwei Scheiben (Vorder-/Hinterrad) aus je 60 Einzelbildern, Austausch über img.src
 * - Räder einzeln oder gemeinsam steuerbar (Auswahl 1/2/3), Drehen mit L/R, Automatik mit A
 * - Erweiterung 1: hüpfender Hase als Sprite-Sheet
 * - Erweiterung 2: kontinuierliche Drehung (requestAnimationFrame, zeitbasiert)
 */
(() => {
  "use strict";

  // ------------------------------------------------------------ Konfiguration
  const FRAMES = 60;
  const DEG_PER_FRAME = 360 / FRAMES;            // 6°
  const frameUrls = (dir) =>
    Array.from({ length: FRAMES }, (_, i) => `img/${dir}/rad_${String(i).padStart(2, "0")}.webp`);

  const BUNNY_FRAMES = 12;
  const BUNNY_FRAME_PX = 220;
  const BUNNY_FPS = 12;

  // ------------------------------------------------------------ DOM
  const $ = (id) => document.getElementById(id);
  const btnLeft = $("btn-left");
  const btnRight = $("btn-right");
  const btnAuto = $("btn-auto");
  const btnAutoLabel = btnAuto.querySelector(".btn-auto-label");
  const segButtons = [...document.querySelectorAll(".seg")];
  const speed = $("speed");
  const speedValue = $("speed-value");
  const toggleFrame = $("toggle-frame");
  const frameImg = $("frame");
  const status = $("status");

  const bunny = $("bunny");
  const btnBunny = $("btn-bunny");
  const btnBunnyLabel = btnBunny.querySelector(".btn-bunny-label");
  const bunnyReadout = $("bunny-readout");
  const sheetMarker = $("sheet-marker");

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ------------------------------------------------------------ Räder
  function createWheel(key, name, dir) {
    return {
      key,
      name,
      img: $(`wheel-${key}`),
      card: $(`card-${key}`),
      readout: $(`readout-${key}`),
      urls: frameUrls(dir),
      index: 0,
      direction: 1,          // +1 = rechts/vorwärts (Uhrzeigersinn), -1 = links/rückwärts
      auto: false,
      acc: 0,                // Zeitakkumulator (ms)
    };
  }

  const wheels = {
    rear: createWheel("rear", "Hinterrad", "hinterrad"),
    front: createWheel("front", "Vorderrad", "vorderrad"),
  };

  const state = {
    ready: false,
    selection: "both",     // "rear" | "front" | "both"
    fps: Number(speed.value),
    bunnyIndex: 0,
    bunnyPlaying: !reducedMotion,
    bunnyAcc: 0,
    lastTime: null,
    rafId: null,
  };

  const selectedWheels = () =>
    state.selection === "both" ? [wheels.rear, wheels.front] : [wheels[state.selection]];
  const dirWord = (d) => (d > 0 ? "vorwärts" : "rückwärts");

  // ------------------------------------------------------------ Bilder laden
  function loadImage(url, onDone) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => {
        const done = () => { onDone(); resolve(img); };
        (img.decode ? img.decode() : Promise.resolve()).then(done, done);
      };
      img.onerror = () => reject(new Error(`Bild konnte nicht geladen werden: ${url}`));
      img.src = url;
    });
  }

  async function preload() {
    const urls = [...wheels.rear.urls, ...wheels.front.urls, frameImg.getAttribute("src"), bunny.getAttribute("src")];
    let loaded = 0;
    const progress = () => {
      loaded += 1;
      if (loaded % 6 === 0 || loaded === urls.length) {
        setStatus(`Bilder werden geladen … ${loaded} von ${urls.length}`);
      }
    };
    const results = await Promise.allSettled(urls.map((u) => loadImage(u, progress)));
    const failed = results.filter((r) => r.status === "rejected");
    if (failed.length) {
      failed.forEach((f) => console.error(f.reason));
      throw new Error(failed[0].reason.message + (failed.length > 1 ? ` (und ${failed.length - 1} weitere)` : ""));
    }
  }

  // ------------------------------------------------------------ Darstellung
  function renderWheel(w) {
    w.img.src = w.urls[w.index];
    const angle = w.index * DEG_PER_FRAME;
    w.readout.textContent = w.auto ? `${angle}°, dreht ${dirWord(w.direction)}` : `${angle}°, steht`;
  }

  function renderSelection() {
    segButtons.forEach((b) => b.setAttribute("aria-checked", String(b.dataset.target === state.selection)));
    const sel = selectedWheels();
    Object.values(wheels).forEach((w) => {
      const on = sel.includes(w);
      w.img.classList.toggle("is-selected", on);
      w.card.classList.toggle("is-selected", on);
    });
    // Auto-Button zeigt, was ein Druck auf A für die Auswahl bewirkt
    const anyAuto = sel.some((w) => w.auto);
    btnAuto.setAttribute("aria-pressed", String(anyAuto));
    btnAutoLabel.textContent = anyAuto ? "Drehung anhalten" : "Automatisch drehen";
  }

  // ------------------------------------------------------------ Aktionen
  function select(target) {
    state.selection = target;
    renderSelection();
    const label = target === "both" ? "Beide Räder" : wheels[target].name;
    setStatus(`${label} ausgewählt.`);
  }

  function rotate(dir) {
    if (!state.ready) return;
    const sel = selectedWheels();
    const changed = [];
    sel.forEach((w) => {
      if (w.auto) {
        if (w.direction !== dir) changed.push(w.name);
        w.direction = dir;                       // während der Automatik: Richtung wechseln
      } else {
        w.direction = dir;
        w.index = (w.index + dir + FRAMES) % FRAMES;
      }
      renderWheel(w);
    });
    if (changed.length) setStatus(`${changed.join(" und ")} dreht jetzt ${dirWord(dir)}.`);
  }

  function toggleAuto() {
    if (!state.ready) return;
    const sel = selectedWheels();
    const start = !sel.some((w) => w.auto);      // läuft eins, wird alles Ausgewählte angehalten
    sel.forEach((w) => { w.auto = start; w.acc = 0; renderWheel(w); });
    renderSelection();
    const who = sel.length > 1 ? "beider Räder" : `des ${sel[0].name}s`;
    setStatus(start
      ? `Automatische Drehung ${who} läuft. A hält sie an.`
      : `Automatische Drehung ${who} angehalten.`);
    ensureLoop();
  }

  // ------------------------------------------------------------ Hase
  function renderBunny() {
    bunny.style.transform = `translateX(${-state.bunnyIndex * BUNNY_FRAME_PX}px)`;
    sheetMarker.style.transform = `translateX(${state.bunnyIndex * (BUNNY_FRAME_PX / 2)}px)`;
    bunnyReadout.textContent = `Phase ${state.bunnyIndex + 1} von ${BUNNY_FRAMES}`;
  }

  function setBunny(on) {
    state.bunnyPlaying = on;
    state.bunnyAcc = 0;
    btnBunny.setAttribute("aria-pressed", String(on));
    btnBunnyLabel.textContent = on ? "Hasen anhalten" : "Hasen hüpfen lassen";
    ensureLoop();
  }

  // ------------------------------------------------------------ Animationsschleife
  const anyRunning = () => wheels.rear.auto || wheels.front.auto || state.bunnyPlaying;

  function ensureLoop() {
    if (anyRunning() && state.rafId === null) {
      state.lastTime = null;
      state.rafId = requestAnimationFrame(tick);
    }
  }

  function advance(acc, dt, fps) {
    // liefert [Anzahl Schritte, Rest-Akkumulator] – bildratenunabhängig
    const interval = 1000 / fps;
    acc += dt;
    const steps = Math.floor(acc / interval);
    return [steps, acc - steps * interval];
  }

  function tick(now) {
    // erster Frame bzw. nach langer Pause (Tab im Hintergrund): kein Zeitsprung
    const dt = state.lastTime === null ? 0 : Math.min(now - state.lastTime, 250);
    state.lastTime = now;

    Object.values(wheels).forEach((w) => {
      if (!w.auto) return;
      const [steps, acc] = advance(w.acc, dt, state.fps);
      w.acc = acc;
      if (steps) {
        w.index = (((w.index + w.direction * steps) % FRAMES) + FRAMES) % FRAMES;
        renderWheel(w);
      }
    });

    if (state.bunnyPlaying) {
      const [steps, acc] = advance(state.bunnyAcc, dt, BUNNY_FPS);
      state.bunnyAcc = acc;
      if (steps) {
        state.bunnyIndex = (state.bunnyIndex + steps) % BUNNY_FRAMES;
        renderBunny();
      }
    }

    state.rafId = anyRunning() ? requestAnimationFrame(tick) : null;
  }

  // ------------------------------------------------------------ Hilfen
  function setStatus(text, isError = false) {
    status.textContent = text;
    status.classList.toggle("is-error", isError);
  }

  function flash(btn) {
    btn.classList.add("is-flash");
    setTimeout(() => btn.classList.remove("is-flash"), 120);
  }

  // ------------------------------------------------------------ Eingaben
  btnLeft.addEventListener("click", () => rotate(-1));
  btnRight.addEventListener("click", () => rotate(1));
  btnAuto.addEventListener("click", toggleAuto);
  btnBunny.addEventListener("click", () => setBunny(!state.bunnyPlaying));
  segButtons.forEach((b) => b.addEventListener("click", () => select(b.dataset.target)));
  Object.values(wheels).forEach((w) => w.img.addEventListener("click", () => select(w.key)));

  // Radio-Gruppe: Pfeiltasten wechseln die Auswahl (WAI-ARIA Radio Group Pattern)
  document.querySelector(".select").addEventListener("keydown", (e) => {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)) return;
    e.preventDefault();
    const i = segButtons.findIndex((b) => b.dataset.target === state.selection);
    const d = e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 1;
    const next = segButtons[(i + d + segButtons.length) % segButtons.length];
    select(next.dataset.target);
    next.focus();
  });

  speed.addEventListener("input", () => {
    state.fps = Number(speed.value);
    speedValue.textContent = `${state.fps} Bilder/s`;
  });

  toggleFrame.addEventListener("change", () => {
    frameImg.classList.toggle("is-hidden", !toggleFrame.checked);
    setStatus(toggleFrame.checked ? "Rahmen eingeblendet." : "Rahmen ausgeblendet – nur die beiden Scheiben sind zu sehen.");
  });

  const KEY_TARGET = { 1: "rear", 2: "front", 3: "both" };

  document.addEventListener("keydown", (e) => {
    // Browser-/System-Kürzel (Cmd+R, Strg+L, …) nicht abfangen
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.target.closest("input[type=text], textarea, [contenteditable=true]")) return;

    const key = e.key.toLowerCase();
    if (!["l", "r", "a", "h", "1", "2", "3"].includes(key)) return;
    e.preventDefault();
    // Gehaltene Taste: kein automatisches Weiterdrehen – jeder Schritt braucht einen neuen Tastendruck
    if (e.repeat) return;

    switch (key) {
      case "l": rotate(-1); flash(btnLeft); break;
      case "r": rotate(1); flash(btnRight); break;
      case "a": toggleAuto(); flash(btnAuto); break;
      case "h": setBunny(!state.bunnyPlaying); flash(btnBunny); break;
      default: select(KEY_TARGET[key]);
    }
  });

  // ------------------------------------------------------------ Start
  async function init() {
    setBunny(state.bunnyPlaying);
    renderBunny();
    renderSelection();
    try {
      await preload();
      state.ready = true;
      [btnLeft, btnRight, btnAuto].forEach((b) => (b.disabled = false));
      Object.values(wheels).forEach(renderWheel);
      setStatus("Bereit. Rad wählen mit 1, 2, 3 – drehen mit L und R, automatisch mit A.");
      console.info(`Rennrad: ${FRAMES * 2} Rad-Bilder, Rahmen und Hasen-Sprite-Sheet geladen.`);
    } catch (err) {
      console.error(err);
      setStatus(`${err.message}. Prüfen Sie, ob der Ordner img/ vollständig auf den Server hochgeladen wurde.`, true);
    }
  }

  init();
})();
