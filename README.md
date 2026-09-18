# Asistente y Analista de Dominó Profesional en Tiempo Real ("Domino Vamos")

Sistema analista de dominó profesional para la aplicación móvil **Domino Vamos** (modalidad 2 vs 2, 28 fichas sin pozo, meta 100 puntos), impulsado por **OpenCV**, **Inferencia Bayesiana de Pases**, y un servidor **FastAPI** de baja latencia (< 100 ms) con un dashboard web y HUD flotante ("nubecita" y flechas tácticas).

---

## Estructura del Proyecto

* **`game_logic.py`**: Motor matemático y de teoría de juegos:
  * Universo cerrado de 28 fichas.
  * Inferencia de pases determinista (cuando un rival pasa ante $(A, B)$, se descartan esos palos con $100\%$ de certeza).
  * Algoritmo de Tranque Ofensivo: cálculo de puntos en mano para forzar cierres ventajosos (como el `[0|0]` en la partida analizada).
  * Apoyo al compañero (`lucho`) y bloqueo al rival de la derecha (`luifermen`) y de la izquierda (`Jesus`).
* **`vision.py`**: Procesamiento de imagen con OpenCV:
  * Detección del temporizador circular verde de turno (10-15s) sobre el avatar de Hero.
  * Extracción y conteo de puntos de las fichas en el atril inferior.
  * Detección del evento `PASAR` (bocadillo naranja).
  * Conteo de fichas restantes de cada jugador (7 a 1).
* **`server.py`**: API REST en FastAPI que procesa frames en $< 100$ ms y sirve la interfaz web.
* **`interface/`**: Dashboard web moderno con HUD superpuesto:
  * **La "Nubecita" Flotante:** Notificación táctica en pantalla que indica: *"¡Juega [X|Y] a la izquierda/derecha!"*
  * **Flecha orientadora:** Apunta a la ficha en atril a jugar.
  * **Visualización de Dominó Real:** Renderizado de la ficha con puntos negros nítidos y resplandor dorado.
  * **Captura en Vivo:** Compatible con *Compartir Pantalla* (`getDisplayMedia`), *Webcam* o *Carga de Capturas*.
* **`test_logic.py`**: Suite de pruebas unitarias para validar las reglas de salida, tranque y pases.
* **`requirements.txt`**: Lista de dependencias del entorno.

---

## Instalación y Puesta en Marcha

### 1. Instalar dependencias
Abre una terminal en la carpeta del proyecto y ejecuta:
```bash
pip install -r requirements.txt
```

### 2. Ejecutar las pruebas de lógica
```bash
python test_logic.py
```

### 3. Iniciar el Servidor del Asistente
```bash
python server.py
```
O directamente con Uvicorn:
```bash
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Abrir la Interfaz Web
Abre tu navegador (Chrome, Edge o Firefox) en:
👉 **`http://localhost:8000`**

---

## Cómo Usarlo Durante una Partida de Domino Vamos

1. Abre **Domino Vamos** en tu emulador de Android (BlueStacks, LDPlayer, Nox) o conéctalo por cable/red con tu móvil (Scrcpy / Screen Mirror).
2. En el Dashboard Web (`http://localhost:8000`), pulsa **🖥️ Compartir Pantalla** y selecciona la ventana de Domino Vamos.
3. El Asistente:
   * Detectará automáticamente cuándo se ilumina el círculo verde de tu turno.
   * Leerá tus fichas en atril.
   * Mostrará la **nubecita** y la **flecha** señalándote la ficha óptima a jugar en menos de 100 ms.
