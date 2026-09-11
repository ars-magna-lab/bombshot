#!/usr/bin/env python3
"""
Genera los sonidos del TOTEM DEL CHAMAN (bombshot v2, fiesta dino-neandertal).

Salida (en ./out/), todo FLAC 48 kHz mono 16 bits (formato nativo del
pipeline de anuncios del Voice PE, ver generar_audio.guardar):

  fuego.flac    crepitar + llamarada     (elemento 0, LED ROJO)     0.6 s  } los cuatro
  agua.flac     chapoteo + burbujas      (elemento 1, LED VERDE)    0.6 s  } elementos
  aire.flac     rafaga de viento         (elemento 2, LED AZUL)     0.6 s  } del Simon,
  tierra.flac   golpe de roca + pedrisco (elemento 3, LED AMARILLO) 0.6 s  } misma duracion
  armar.flac    redoble de tambor + sonajero al armar  ~1.3 s
  turno.flac    sonajero corto: "te toca"              ~0.5 s
  erupcion.flac rumble + rugido grande + explosion     ~7.6 s  (derrota)
  tribu.flac    tambores de fiesta + los 4 elementos   ~5.8 s  (victoria)
  voz_fuego/agua/aire/tierra.flac  la palabra dicha  0.9 s fijos  (lo que
                el totem dice al mostrar la secuencia; el aro pone el color)
  coge_hueso.flac  voz "Coge un hueso."                (premio)

Los cuatro sonidos de elemento duran EXACTAMENTE lo mismo (0.6 s) a
proposito: asi el firmware muestra la secuencia con un unico `delay` por
paso, sin tener que saber que elemento esta sonando.

SONIDOS SINTETIZADOS, NO GRABADOS. Se valoro usar grabaciones libres
(freesound CC0, Wikimedia Commons), pero para un Simon lo que hace falta
son cuatro cues de 0.6 s que se distingan entre si a la primera y en un
altavoz sin graves, y un recorte de 0.6 s de una grabacion de viento o de
fuego es un soplido de ruido indistinguible del otro. Sintetizandolos se
controla el timbre: cada elemento tiene un "gesto" propio (el fuego
crepita, el agua burbujea con chirridos ascendentes, el aire silba con un
swell, la tierra golpea y luego rueda). Si aun asi se quiere probar con
grabaciones, `importar_clip.py` deja cualquier WAV/MP3 en el formato y
duracion exactos que espera el firmware.

REGLA DEL ALTAVOZ (heredada de la v1, ver CLAUDE.md punto 4): el altavoz
del Voice PE no baja de ~250 Hz. Todo lo que quiera sonar "grave" se
construye con saturacion (armonicos) y se le recorta el grave real
despues. Por eso el golpe de la tierra no es un bombo de 60 Hz sino un
tom de 200-400 Hz con armonicos, y el rugido del volcan vive en
300-1500 Hz aunque su fundamental este mas abajo.

Reutiliza las utilidades de generar_audio.py (filtro, saturar, reverberar,
explosion_grande, guardar) y la voz de generar_voces.py.

Uso:
  python3 generar_totem.py
  python3 generar_totem.py --seed 3     # otra "toma" de los sonidos ruidosos
"""

import argparse
import os
import subprocess

import numpy as np

import generar_audio as ga
import generar_voces as gv

SR = ga.SR
PASO = 0.60   # duracion fija de cada sonido de elemento, en segundos


# ---------------------------------------------------------------- utilidades
def fijar(x, dur):
    """Recorta o rellena con silencio hasta `dur` segundos exactos, con un
    fundido de salida corto para que el corte no haga clic."""
    n = int(dur * SR)
    out = np.zeros(n)
    m = min(n, len(x))
    out[:m] = x[:m]
    nf = int(0.015 * SR)
    out[n - nf:] *= np.linspace(1, 0, nf)
    return out


def tono(freqs, n, armonicos=((1, 1.0),)):
    """Oscilador con frecuencia variable (`freqs` es un array de n Hz) y
    una lista de (multiplo, amplitud) para los armonicos."""
    fase = 2 * np.pi * np.cumsum(freqs) / SR
    out = np.zeros(n)
    for mult, amp in armonicos:
        out += amp * np.sin(fase * mult)
    return out


def env_adsr(n, ataque=0.005, caida=8.0):
    return ga.envolvente(n, ataque=ataque, decay=caida)


def tambor(rng, dur=PASO):
    """Tronco hueco golpeado (el tambor del chaman): tono que cae de 440 a
    260 Hz con armonicos y saturacion para que el altavoz lo lea como
    grave, y un chasquido de madera en el ataque. Lo usan armar(), tribu()
    y el golpe de tierra()."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    # 440 -> 260 Hz: mas agudo que un tom "de verdad" a proposito. Con la
    # fundamental en 190 Hz solo el 16 % de la energia quedaba por encima
    # de 300 Hz (medido) y el altavoz no lo radiaba; asi queda >55 %.
    f = 260.0 + 180.0 * np.exp(-18.0 * t)
    cuerpo = tono(f, n, armonicos=((1, 1.0), (2, 0.6), (3, 0.35), (4, 0.15))) * env_adsr(n, caida=7.0)
    madera = rng.standard_normal(n) * np.exp(-60.0 * t)
    madera = ga.filtro(madera, 600, 3500) * 0.7
    x = ga.saturar(cuerpo * 1.6 + madera, drive=3.0)
    x = ga.filtro(x, lo=230)
    return fijar(x, dur)


def crepitar(rng, n, densidad, lo, hi, largo_s=0.012, caida=120.0):
    """Chasquidos sueltos al azar (brasas, pedrisco): `densidad` por
    segundo, cada uno de `largo_s` con caida exponencial, en la banda
    lo-hi."""
    out = np.zeros(n)
    dur = n / SR
    m = int(largo_s * SR)
    for _ in range(int(densidad * dur)):
        pos = rng.random() * (dur - largo_s)
        c = rng.standard_normal(m) * np.exp(-caida * np.arange(m) / SR)
        ga.mezclar(out, c * (0.4 + 0.6 * rng.random()), pos)
    return ga.filtro(out, lo, hi)


def rugido(rng, dur=1.3, f_ini=110.0, f_fin=70.0, drive=5.0):
    """Rugido de dinosaurio (para la erupcion): diente de sierra grave con
    vibrato lento y un tremolo rapido (la "garganta"), pasado por una banda
    de formantes y saturado a lo bestia. El grave real se quita al final:
    los armonicos ya hacen el trabajo."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = f_ini + (f_fin - f_ini) * (t / t[-1]) + 6.0 * np.sin(2 * np.pi * 4.0 * t)
    arm = tuple((k, 1.0 / k) for k in range(1, 14))   # diente de sierra
    voz = tono(f, n, armonicos=arm)
    garganta = 1.0 + 0.45 * np.sign(np.sin(2 * np.pi * 27.0 * t))
    aliento = ga.filtro(rng.standard_normal(n), 500, 3000) * 0.35
    x = voz * garganta + aliento
    x = ga.filtro(x, 250, 2200)
    x = ga.saturar(x * 1.5, drive=drive)
    x = ga.filtro(x, lo=200)
    env = np.minimum(1.0, t / 0.05) * np.minimum(1.0, (t[-1] - t) / 0.12)
    return x * env


# ---------------------------------------------------------------- los cuatro elementos
#  indice  LED       elemento   gesto sonoro
#     0    rojo      FUEGO      crepitar de brasas + llamarada que sube
#     1    verde     AGUA       chapoteo + burbujas (chirridos ascendentes)
#     2    azul      AIRE       rafaga de viento con silbido
#     3    amarillo  TIERRA     golpe de roca + pedrisco rodando
#  El orden es el de los indices del firmware (elemento 0..3).

def fuego(rng):
    """Brasas crepitando (chasquidos brillantes, densos) y una llamarada:
    ruido en 300-2500 Hz con un swell rapido y un tremolo de 14 Hz que
    es lo que hace que el oido diga "llama" y no "viento"."""
    n = int(PASO * SR)
    t = np.arange(n) / SR
    brasas = crepitar(rng, n, densidad=90, lo=1200, hi=7000, largo_s=0.008, caida=200.0)
    llama = ga.filtro(ga.ruido_marron(n, rng), 300, 2500)
    swell = np.minimum(1.0, t / 0.12) * np.exp(-2.2 * t)
    llama *= swell * (1.0 + 0.5 * np.sin(2 * np.pi * 14.0 * t))
    x = ga.saturar(llama * 1.3 + brasas * 1.1, drive=2.2)
    x = ga.filtro(x, lo=280)
    return fijar(x, PASO)


def agua(rng):
    """Un chapoteo (rafaga de ruido agudo con ataque instantaneo) seguido de
    burbujas: chirridos senoidales cortos que SUBEN de tono, que es la
    firma acustica de una burbuja. Es el mas reconocible de los cuatro."""
    n = int(PASO * SR)
    t = np.arange(n) / SR
    chapoteo = rng.standard_normal(n) * np.exp(-22.0 * t)
    chapoteo = ga.filtro(chapoteo, 900, 7000) * 0.9
    burbujas = np.zeros(n)
    for _ in range(11):
        inicio = 0.05 + rng.random() * 0.45
        largo = 0.04 + rng.random() * 0.05
        m = int(largo * SR)
        tt = np.arange(m) / SR
        f0 = 500.0 + rng.random() * 700.0
        f = f0 * (1.0 + 1.4 * tt / largo)          # sube ~2.4x: "blop"
        b = tono(f, m) * np.exp(-25.0 * tt) * np.minimum(1.0, tt / 0.003)
        ga.mezclar(burbujas, b * (0.5 + 0.5 * rng.random()), inicio)
    goteo = ga.filtro(ga.ruido_marron(n, rng), 800, 4000) * 0.12 * np.exp(-3.0 * t)
    x = chapoteo + burbujas * 1.2 + goteo
    # Saturacion suave: el chapoteo es muy picudo y sin esto el clip queda
    # a la mitad de volumen percibido que la tierra (RMS 0.11 frente a 0.43).
    x = ga.saturar(x * 2.2, drive=2.0)
    return fijar(x, PASO)


def aire(rng):
    """Rafaga de viento: ruido en 400-4000 Hz con un swell lento (sube en
    0.25 s, baja en 0.35 s) y, por encima, un silbido tenue que barre de
    900 a 1700 Hz. Sin el silbido, el viento y el fuego se confunden en
    un altavoz pequeño."""
    n = int(PASO * SR)
    t = np.arange(n) / SR
    swell = np.interp(t, [0, 0.25, PASO], [0.05, 1.0, 0.0]) ** 1.5
    viento = ga.filtro(rng.standard_normal(n), 400, 4000) * swell
    f = np.interp(t, [0, 0.3, PASO], [900.0, 1700.0, 1200.0])
    f *= 1.0 + 0.02 * np.sin(2 * np.pi * 5.0 * t)
    silbido = tono(f, n) * swell * 0.35
    x = ga.saturar((viento * 0.9 + silbido) * 1.8, drive=1.8)   # mismo motivo que en agua()
    return fijar(x, PASO)


def tierra(rng):
    """Golpe de roca y pedrisco: un tom seco y saturado (ver tambor()) y
    despues piedras rodando: chasquidos mas graves y mas lentos que las
    brasas del fuego (300-2500 Hz, 45 por segundo, cada uno mas largo)."""
    n = int(PASO * SR)
    t = np.arange(n) / SR
    golpe = tambor(rng, dur=0.3)
    piedras = crepitar(rng, n, densidad=45, lo=300, hi=2500, largo_s=0.03, caida=60.0)
    piedras *= np.interp(t, [0, 0.08, 0.2, PASO], [0.0, 0.3, 1.0, 0.4])
    x = np.zeros(n)
    ga.mezclar(x, golpe, 0.0)
    x += piedras * 0.9
    x = ga.saturar(x, drive=1.6)
    x = ga.filtro(x, lo=250)
    return fijar(x, PASO)


ELEMENTOS = (("fuego", fuego), ("agua", agua), ("aire", aire), ("tierra", tierra))

# Voces (espeak-ng). Las cuatro palabras de elemento se rellenan a PASO_VOZ
# segundos exactos, por el mismo motivo que los sonidos: un solo delay por
# paso en el firmware. Son lo que el totem DICE al mostrar la secuencia
# (version simplificada de 2026-09-11: sin LEDs externos, el aro se pone
# del color del elemento y el Voice PE dice su nombre).
PASO_VOZ = 0.9
VOCES = (
    ("voz_fuego", "Fuego.", PASO_VOZ),
    ("voz_agua", "Agua.", PASO_VOZ),
    ("voz_aire", "Aire.", PASO_VOZ),
    ("voz_tierra", "Tierra.", PASO_VOZ),
    ("coge_hueso", "Coge un hueso.", None),
)


# ---------------------------------------------------------------- resto
def sonajero(rng, dur=0.5, golpes=3):
    """Maracas / sonajero de semillas: rafagas de ruido agudo."""
    n = int(dur * SR)
    out = np.zeros(n)
    for i in range(golpes):
        m = int(0.09 * SR)
        r = rng.standard_normal(m) * np.exp(-40.0 * np.arange(m) / SR)
        ga.mezclar(out, r, 0.02 + i * (dur - 0.12) / max(1, golpes - 1) * 0.8)
    return ga.filtro(out, 2000, 9000)


def armar(rng):
    """Redoble de tambor que acelera y remata con el sonajero: 'el ritual
    empieza'."""
    out = np.zeros(int(1.3 * SR))
    pos = 0.0
    paso = 0.22
    while pos < 0.85:
        ga.mezclar(out, tambor(rng)[: int(0.25 * SR)] * (0.6 + 0.4 * pos), pos)
        pos += paso
        paso *= 0.78
    ga.mezclar(out, sonajero(rng, dur=0.45, golpes=4) * 0.8, 0.85)
    return out


def erupcion(rng):
    """Derrota: el volcan. Rumble que crece, un rugido gordo por encima y
    la explosion grande de la v1 rematando."""
    boom = ga.explosion_grande(rng)
    intro = 1.4
    out = np.zeros(int(intro * SR) + len(boom))

    n = int(1.6 * SR)
    rumble = ga.filtro(ga.ruido_marron(n, rng), 150, 900) * np.linspace(0.15, 1.0, n) ** 2
    ga.mezclar(out, rumble * 0.7, 0.0)
    ga.mezclar(out, rugido(rng) * 0.9, 0.25)
    ga.mezclar(out, boom, intro)
    return out


def tribu(rng):
    """Victoria: tambores de fiesta (patron de 4 tiempos, acelerando un
    poco), sonajero a corcheas, los cuatro elementos en arpegio y un
    silbido largo que sube al final."""
    dur = 5.0
    out = np.zeros(int(dur * SR))
    tam = tambor(rng)[: int(0.3 * SR)]
    pos = 0.0
    beat = 0
    tempo = 0.30
    while pos < 3.9:
        acento = 1.0 if beat % 4 == 0 else 0.55
        ga.mezclar(out, tam * acento, pos)
        if beat % 2 == 1:
            ga.mezclar(out, sonajero(rng, dur=0.2, golpes=1) * 0.5, pos)
        pos += tempo
        tempo = max(0.22, tempo * 0.985)
        beat += 1
    for i, (_, fn) in enumerate(ELEMENTOS):
        ga.mezclar(out, fn(rng) * 0.7, 3.95 + i * 0.22)

    n = int(1.0 * SR)
    t = np.arange(n) / SR
    f = np.interp(t, [0, 1.0], [1300.0, 2400.0]) * (1 + 0.01 * np.sin(2 * np.pi * 6 * t))
    ga.mezclar(out, tono(f, n) * np.minimum(1, t / 0.05) * np.minimum(1, (t[-1] - t) / 0.2) * 0.5, 3.0)
    return ga.reverberar(out, rng, dur_cola=0.8, mezcla=0.18)


# ---------------------------------------------------------------- main
def guardar_flac(nombre, datos, outdir):
    """Solo FLAC (guardar() de la v1 saca siempre MP3; aqui el MP3 sobra)."""
    ga.guardar(nombre, datos, outdir, flac=True)
    os.remove(os.path.join(outdir, nombre + ".mp3"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out")
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--velocidad", type=int, default=135, help="wpm de la voz")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    rng = np.random.default_rng(args.seed)

    print("Generando sonidos del totem...")
    for nombre, fn in ELEMENTOS:
        guardar_flac(nombre, fn(rng), args.out)
    guardar_flac("armar", armar(rng), args.out)
    guardar_flac("turno", sonajero(rng, dur=0.5, golpes=3), args.out)
    guardar_flac("erupcion", erupcion(rng), args.out)
    guardar_flac("tribu", tribu(rng), args.out)

    print("Generando voces...")
    lib = gv.cargar_libreria()
    sr = lib.espeak_Initialize(gv.AUDIO_OUTPUT_RETRIEVAL, 0, None, 0)
    lib.espeak_SetVoiceByName(b"es")
    lib.espeak_SetParameter(gv.ESPEAK_RATE, args.velocidad, 0)
    for nombre, texto, dur in VOCES:
        pcm = gv.sintetizar(lib, texto)
        flac = os.path.join(args.out, nombre + ".flac")
        gv.guardar_flac(pcm, sr, os.path.join(args.out, nombre + ".wav"), flac)
        if dur:
            # Duracion fija: el firmware muestra la secuencia con un unico
            # delay por paso, asi que las cuatro palabras han de durar igual.
            tmp = flac + ".tmp.flac"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", flac,
                            "-af", f"apad=whole_dur={dur},atrim=0:{dur}",
                            "-ar", "48000", "-ac", "1", "-sample_fmt", "s16", tmp], check=True)
            os.replace(tmp, flac)
        print(f"  {flac}")
    lib.espeak_Terminate()
    print()
    print("Listo. Copia los .flac nuevos a esphome/sounds/ y comprueba las")
    print("duraciones con ffprobe contra los delays de esphome/totem.yaml.")


if __name__ == "__main__":
    main()
