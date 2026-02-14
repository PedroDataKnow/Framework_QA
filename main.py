# ==============================================================================
# SECCIÓN 1: IMPORTACIONES DE LIBRERÍAS
# ==============================================================================
import subprocess                       # Vital: Permite ejecutar comandos de terminal (como 'Locust').
import os                               # Para interactuar con el Sistema Operativo (limpiar pantalla, variables de entorno).
import time                             # para pausar el script (time.sleep) y generar marcas de tiempo (timestamp).
import csv                              # Para leer el archivo de resultados que genera Locust (.csv).
import textwrap                         # para cortar textos largos en varias líneas (usado en la tabla visual).
from itertools import zip_longest       # Para recorrer dos listas de df diferente tamaño al mismo tiempo (en la tabla visual).
import sys

# ==============================================================================
# SECCIÓN 2: CARGA DE DATOS EXTERNOS
# ==============================================================================
try:
    # Intentamos importar la base de datos de ataques desde 'data.py'
    from data import SECURITY_PAYLOADS
except ImportError:
    # manejo de errores: Si el archivo no existe, el programa no se rompe, solo avisa.
    print("⚠️ Error: No se pudo importar SECURITY_PAYLOADS de data.py")
    SECURITY_PAYLOADS = []

DIR_REPORTES = "reports"

# ==============================================================================
#   FUNCIONES DE UTILIDAD Y VISUALIZACIÓN
# ==============================================================================
def limpiar_consola():
    """ Limpia la pantalla de la terminal """
    os.system('cls' if os.name == 'nt' else 'clear')

def mostrar_previa_seguridad():
    """
    Genera una tabla visual en la consola mostrando los vectores de ataque disponibles.
    Sirve para que el usuario observe las opciones qué puede lanzar contra el servidor"
    """
    print(" 🕵️  --- VISTA PREVIA DEL ARSENAL DE SEGURIDAD ---")
    
    # List Comprehensions: Filtramos los pauloads separándolos en dos columnas:
    # 1. Validaciones/Gobernanza (Pruebas "suaves")
    validations = [p['content'] for p in SECURITY_PAYLOADS if "Validation" in p['type'] or "Governance" in p['type']]
    # 2. Inyecciones/Fugas (Pruebas "duras")
    injections = [p['content'] for p in SECURITY_PAYLOADS if "DataLeak" in p['type'] or "Injection" in p['type']]

    # Configuración de la tabla
    ancho = 55
    borde = "+" + "-" * (ancho + 2) + "+" + "-" * (ancho + 2) + "+"
    
    print(borde)
    print(f"| {'🛡️  VALIDATION':^{ancho}} | {'💉  INJECTION':^{ancho}} |")
    print(borde)

    # zip_longest permite iterar ambas listas aunque una sea más larga que la otra (rellena con vacíos)
    for val, inj in zip_longest(validations, injections, fillvalue=""):
        val, inj = str(val), str(inj)
        
        # Protegemos la consola de textos gigantes
        if len(val) > 1000: val = f"[CONTENIDO MASIVO: {len(val)} chars]"

        # Textwrap divide el texto en líneas múltiples si excede el ancho de la columna
        lineas_val = textwrap.wrap(val, width=ancho) or [""]
        lineas_inj = textwrap.wrap(inj, width=ancho) or [""]
        max_altura = max(len(lineas_val), len(lineas_inj))

        # Imprimimos línea por línea para mantener la lineación de la tabla
        for i in range(max_altura):
            txt_v = lineas_val[i] if i < len(lineas_val) else ""
            txt_i = lineas_inj[i] if i < len(lineas_inj) else ""
            print(f"| {txt_v:<{ancho}} | {txt_i:<{ancho}} |")
        print(borde)
    print(" ")

# ==============================================================================
# SECCIÓN 4: GENERACIÓN DE REPORTES (POST-PROCESAMIENTO)
# ==============================================================================
def inyectar_html_en_reporte(ruta_html, html_analisis, estado_final):
    """
    Toma el HTML estándar generado por Locust y le inyecta un bloque personalizado
    con el resumen ejecutivo (PASS/FAIL) al final del archivo.
    """
    if not os.path.exists(ruta_html): return

    # Definición de colores según el estado (Verde = PASS, Rojo = FAIL)
    if estado_final == "PASS":
        c, bg, ico = "#28a745", "#d4edda", "✅ APROBADO"
        txt = "#155724"
    else:
        c, bg, ico = "#dc3545", "#f8d7da", "❌ FALLIDO"
        txt = "#721c24"

    # Plantilla HTML del bloque de resumen
    bloque = f"""
    <div style="margin: 30px auto; width: 90%; font-family: sans-serif;">
        <div style="border: 2px solid {c}; background-color: {bg}; border-radius: 8px;">
            <div style="background-color: {c}; color: white; padding: 10px 20px; font-weight: bold;">{ico}</div>
            <div style="padding: 20px; color: {txt}; line-height: 1.5;">{html_analisis}</div>
            <div style="padding: 10px 20px; font-size: 12px; text-align: right; opacity: 0.7;">QA Automation Suite</div>
        </div>
    </div>
    </body>"""
    
    try:
        # Leemos el archivo original
        with open(ruta_html, "r", encoding="utf-8") as f: contenido = f.read()
        # Reemplazamos la etiqueta de cierra </body> con nuestro bloque + </body>
        if "</body>" in contenido:
            with open(ruta_html, "a", encoding="utf-8") as f: f.write(contenido.replace("</body>", bloque))
            print(f"✨ Reporte actualizado: {ruta_html}")
    except Exception as e: print(f"⚠️ Error HTML: {e}")

def analizar_resultados(archivo_base, tipo_prueba, total_users, umbral_tiempo_ms):
    """
    Leer el CSV generado por Locust, extrae métricas clave y decide si la prueba pasó o falló.
    """

    print(f"  --- ANALIZANDO RESULTADOS ---")
    ruta_csv = f"{archivo_base}_stats.csv"
    if not os.path.exists(ruta_csv):
        return
    
    stats = {}
    try:
        # Abrimos el CSV y buscamos la fila "Agregated" (Resumen total)
        with open(ruta_csv, mode='r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["Name"] == "Aggregated": stats = row; break
    except: return
    if not stats: return

    try:
        reqs = int(stats["Request Count"])
        fails = int(stats["Failure Count"])
        # Si Locust no recibió respuestas, el valor es "N/A", lo convertimos a 0.0 para evitar crash
        val_95 = stats.get("95%", "0")
        p95 = 0 if val_95 == "N/A" else float(val_95)
    except ValueError:
        print("⚠️ Datos corruptos o vacíos en el CSV.")
        return

    # reqs, fails = int(stats["Request Count"]), int(stats["Failure Count"])
    # p95 = float(stats["95%"])

    mensajes, estado = [], "PASS"

    # --- LÓGICA DE DECISIÓN (PASS/FAIL) SEGPUN ESCENARIO ---
    mensajes.append(f"<strong>Resumen:</strong> {reqs} Peticiones | {fails} Fallos")
    mensajes.append(f"<strong>P95 Latencia:</strong> {p95/1000} Segundos")
    mensajes.append("<hr>")

    

    if tipo_prueba == "1": # CARGA
        mensajes.append("<strong>Modo:</strong> CARGA")
        if fails > 0: estado="FAIL"; mensajes.append("🔴 FALLO: Errores funcionales.")
        elif p95 > umbral_tiempo_ms and fails == 0:
            estado="FAIL"
            mensaje_narrativo = f"""
        <div style="background-color: #fff3cd; color: #856404; padding: 15px; border-left: 5px solid #ffeeba; margin: 10px 0;">
            <strong>⚠️ ALERTA DE EXPERIENCIA DE USUARIO:</strong><br><br>
            Aunque el reporte dice <b>{fails} fallos técnicos</b> (ningún error 500 o 404), 
            la experiencia de usuario es <b>inaceptable</b>.<br><br>
            El sistema no se cayó, pero se volvió extremadamente lento bajo la presión de 
            <b>{total_users} usuarios</b> entrando de golpe.
        </div>
        """
            mensajes.append(mensaje_narrativo)
            mensajes.append(f"🟠 <b>Diagnóstico:</b> Saturación por concurrencia (Latencia P95: {p95/1000} segundos, el <b>tiempo normal de espera sería</b> = {umbral_tiempo_ms/1000} ssegundos).")

            
            # mensajes.append(f"🟠 LENTITUD: El sistema es lento > {umbral_tiempo_ms}ms")
        else: mensajes.append("🟢 APROBADO: Estable.")
    elif tipo_prueba == "2": # ESTRÉS
        mensajes.append("<strong>Modo:</strong> ESTRÉS")
        # En estrés, queremos ver si el sistema falla. Si falla, encontramos el límite (Éxito de la prueba).
        if fails > 0: estado="PASS"; mensajes.append("💥 ÉXITO: Punto de quiebre encontrado (Errores HTTP detectados).")
        else: estado="FAIL"; mensajes.append("🛡️ ROBUSTO: El sistema aguantó la carga sin errores.")
    elif tipo_prueba == "3": # SEGURIDAD
        mensajes.append("<strong>Modo:</strong> SEGURIDAD")
        # En seguridad, cualquier fallo significa que una inyección funcionó (Vulnerabilidad).
        if fails > 0: estado="FAIL"; mensajes.append(f"🚨 VULNERABLE: {fails} fugas/errores.")
        else: mensajes.append("🛡️ SEGURO: Información protegida.")


    # Inyectamos el resultado en HTML
    inyectar_html_en_reporte(f"{archivo_base}.html", "<br>".join(mensajes), estado)


# ==============================================================================
# SECCIÓN 5: ORQUESTADOR PRINCIPAL (CLI)
# ==============================================================================
def ejecutar_prueba():
    limpiar_consola()
    time.sleep(1) 
    print("========================================================")
    print("      FRAMEWORK DE PRUEBAS DE RENDIMIENTO Y SEGURIDAD      ")
    print("========================================================")

    if not os.path.exists(DIR_REPORTES):
        print(f"Creando carpeta de reportes: {DIR_REPORTES}...")
        os.makedirs(DIR_REPORTES, exist_ok=True)

    try:
        # 1. Menú Principal
        print(" Seleccione Escenario:")
        print("   [1] CARGA (Estabilidad)")
        print("   [2] ESTRÉS (Ruptura - Generación IA Masiva)")
        print("   [3] SEGURIDAD (Robo de Información)")
        tipo = input("    Opción: ").strip()

        # 2. Configuración específica para Seguridad
        if tipo == "3":
            # Preguntar si solo quiere ver o ejecutar
            sub_opcion = input("    [V] Ver Payloads  |  [E] Ejecutar Ataque: ").strip().upper()
            if sub_opcion == "V":
                mostrar_previa_seguridad()
                return # Salimos si solo quiere ver
                    
        # 3. Recolección de parámetros de prueba
        endpoint = input(" Ingresa el Endpoint URL: ").strip()
        users = int(input(" Cantidad de usuarios: ").strip())

        if tipo == "2": # Si es ESTRÉS
            duration = 120
            print(f"⏱️  Configuración de ESTRÉS detectada: Duración establecida en {duration}s")
        else: # Si es CARGA (1) o SEGURIDAD (3)
            duration = 60
            print(f"⏱️  Configuración estándar: Duración establecida en {duration}s")

        # if tipo == "1":
        #     sla_valor = input("Tiempo de carga máximo aceptable (SLA) en segundos: ").strip()

        # Nuevas preguntas para SLAs diferenciados
        if tipo == "1":
            sla_load = input("SLA para CARGA (segundos) [Defecto 2.0]: ").strip() or "2.0"
        elif tipo == "2":
            sla_stress = input("SLA para ESTRÉS (segundos) [Defecto 15.0]: ").strip() or "15.0"



        # Validación mínima de duración
        if duration <= 0: duration = 10
        # Cálculo de Spam Rate (Tasa de aparición)
        # Hacemos que los usuarios entren gradualmente durante la primera mitad de la prueba.
        tiempo_subida = duration / 2
        spawn = users / tiempo_subida if tiempo_subida > 0 else users
        print(f"Están ingresando {spawn:.2f} usuarios por segundo.")

        # 4. Configuración de Variables de Entorno
        # Pasamos estos datos a 'Locust_web.py' a través de os.environ
        env_vars = os.environ.copy()
        env_vars["TARGET_PATH"] = endpoint 
        if tipo == "1":
            env_vars["SLA_LOAD"] = sla_load
        elif tipo == "2":
            env_vars["SLA_STRESS"] = sla_stress

        if tipo == "3":
            env_vars["TEST_TYPE"] = "SECURITY"
            print(" 🛡️  INICIANDO PROTOCOLO DE SEGURIDAD...")
        elif tipo == "2":
            env_vars["TEST_TYPE"] = "STRESS"
            print(" 🔥 INICIANDO PROTOCOLO DE ESTRÉS (Ataque de Prompts Masivo)...")
        else:
            env_vars["TEST_TYPE"] = "LOAD"
            print(" ⚖️  INICIANDO PROTOCOLO DE CARGA...")

        # Generamos un nombre de archivo único con la fecha y hora
        timestamp: str = time.strftime("%Y%m%d-%H%M%S")
        archivo = f"Reporte_QA_{timestamp}"

        # Ruta completa: reports/Eeporte_QA_2025...
        ruta_archivo_base = os.path.join(DIR_REPORTES, archivo)

        # 5. CONSTRUCCIÓN Y EJECUCIÓN DEL COMANDO LOCUST
        # Esto equivale a escribir en la terminal: locust -f locust_web.py --headless ...
        comando = [
            sys.executable, "-m", "locust", "-f", "locust_web.py", "--headless",
            "-u", str(users), "-r", str(spawn), "-t", str(duration),
            "--host", endpoint, "--csv", ruta_archivo_base, "--html", f"{ruta_archivo_base}.html"
        ]

        print(f" 🚀 Ejecutando Locust y guardando en '{DIR_REPORTES}/'...")
        # subprocess.run detiene este script hasta que Locust termine
        subprocess.run(comando, env=env_vars, check=False)
        
        # 6. Análisis final
        umbral_final = float(sla_load if tipo == "1" else sla_stress)
        analizar_resultados(ruta_archivo_base, tipo, users, umbral_tiempo_ms=umbral_final * 1000)

    except KeyboardInterrupt: print(" 🛑 Cancelado.")
    except Exception as e: print(f" ❌ Error: {e}")

if __name__ == "__main__":
    ejecutar_prueba()