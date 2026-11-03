"""
Hablar con la mascota.

  hw.py        ¿el equipo puede con la IA? (RAM, CPU, GPU, disco) → nivel
  llm.py       cliente mínimo de Ollama (solo 127.0.0.1): arrancar, bajar
               modelos, conversar en streaming
  phrases.py   modo sin IA: frases escritas por tema y personalidad
  personas.py  personalidades y el «system prompt» de cada una
  voice.py     micrófono + Vosk: «ey <nombre>» y transcribir la frase
  brain.py     el que lo une todo con las mascotas (GLib, hilo principal)

Nada sale del equipo: el audio se procesa en memoria y se descarta, el modelo
corre en local y el historial de la charla solo vive en RAM.
"""
