#!/usr/bin/env python3
"""
Convierte una grabacion cualquiera (WAV, MP3, OGG, FLAC...) en un clip con
el formato y la duracion EXACTOS que espera el firmware del totem:
FLAC 48 kHz mono 16 bits, recortado/rellenado a `--dur` segundos, con
fundido de salida, paso alto a 250 Hz (el altavoz del Voice PE no baja de
ahi, ver CLAUDE.md punto 4) y volumen normalizado.

Sirve para probar sonidos libres (freesound.org con filtro CC0, Wikimedia
Commons con licencia PD/CC0) en lugar de los sintetizados por
generar_totem.py, sin tocar nada del YAML: basta con que el fichero de
salida se llame igual (fuego, agua, aire, tierra) y dure lo mismo.

OJO CON LA LICENCIA: el repo es publico. Solo CC0 / dominio publico, o
CC-BY apuntando la atribucion en docs/v2-plan.md. Nada de "gratis para
uso personal" (BBC, Pixabay, Zapsplat...): eso no permite redistribuirlo
en un repositorio.

Uso:
  python3 importar_clip.py grabacion.wav fuego                # 0.6 s desde el principio
  python3 importar_clip.py viento.mp3 aire --inicio 2.3       # recorta desde el segundo 2.3
  python3 importar_clip.py tambores.ogg tribu --dur 5.8       # otro largo (cambia el delay en el YAML)

Requisitos: ffmpeg en el PATH. numpy es opcional (para el aviso de graves).
"""

import argparse
import os
import subprocess


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("entrada", help="fichero de audio de origen")
    ap.add_argument("nombre", help="nombre de salida sin extension (fuego, agua, aire, tierra...)")
    ap.add_argument("--dur", type=float, default=0.6, help="duracion exacta en segundos (defecto 0.6)")
    ap.add_argument("--inicio", type=float, default=0.0, help="segundo desde el que recortar")
    ap.add_argument("--paso-alto", type=float, default=250.0, help="Hz del paso alto (0 = ninguno)")
    ap.add_argument("--out", default="out")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    destino = os.path.join(args.out, args.nombre + ".flac")
    fundido = min(0.03, args.dur / 4)

    filtros = []
    if args.paso_alto > 0:
        filtros.append(f"highpass=f={args.paso_alto}:poles=2")
    filtros += [
        "loudnorm=I=-14:TP=-1.0:LRA=7",          # volumen parejo entre clips
        f"apad=whole_dur={args.dur}",             # rellena si es corto
        f"atrim=0:{args.dur}",                    # recorta si es largo
        f"afade=t=out:st={args.dur - fundido}:d={fundido}",
        "aresample=48000",
    ]
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-ss", str(args.inicio), "-i", args.entrada,
         "-af", ",".join(filtros),
         "-ac", "1", "-ar", "48000", "-sample_fmt", "s16", "-c:a", "flac",
         destino],
        check=True,
    )
    dur = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", destino], capture_output=True, text=True).stdout.strip()
    print(f"{destino}  ({float(dur):.2f} s)")

    try:
        import numpy as np
        raw = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", destino, "-f", "f32le", "-ac", "1", "-ar", "48000", "-"],
            capture_output=True).stdout
        x = np.frombuffer(raw, np.float32).astype(float)
        X = np.abs(np.fft.rfft(x)) ** 2
        fr = np.fft.rfftfreq(len(x), 1 / 48000)
        pct = 100 * X[fr > 300].sum() / X.sum()
        print(f"  energia por encima de 300 Hz: {pct:.0f} %"
              + ("" if pct > 50 else "  <-- OJO: sonara flojo en el Voice PE"))
    except ImportError:
        pass
    print("Copialo a esphome/sounds/ y, si la duracion no es la de antes, cambia su delay en totem.yaml.")


if __name__ == "__main__":
    main()
