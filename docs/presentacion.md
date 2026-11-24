# Presentación: datos de ejemplo y enlace público

Para que el profesor pruebe el sistema (en la clase o desde su casa), se enciende en una de
nuestras computadoras con una **base aparte llena de datos de ejemplo** y se publica con un
**enlace https gratuito** de Cloudflare.

- La base de trabajo (`clinica_familiar`) **no se toca**: la presentación usa `clinica_presentacion`.
- **Todo es inventado:** pacientes, DUI, consultas e inventario.
- El enlace funciona **mientras la computadora esté encendida** con `encender.bat` abierto. Si se
  apaga o se cierra la ventana, se cae; al volver a encender, **el enlace cambia**.

## Una sola vez

1. **Instalar cloudflared** (el programa del enlace público). En PowerShell:

   ```powershell
   winget install --id Cloudflare.cloudflared
   ```

   Después cierren y vuelvan a abrir la terminal.

2. **Instalar las dependencias nuevas** (WhiteNoise y Waitress):

   ```powershell
   .\venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

3. **Ponerle al `.env` una clave secreta propia** (la que trae `settings.py` está en GitHub y no
   sirve para abrir el sistema desde internet). Este comando la agrega sola:

   ```powershell
   .\venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key as k; open('.env','a',encoding='utf-8').write(chr(10)+'SECRET_KEY='+chr(39)+k()+chr(39)+chr(10))"
   ```

4. **El teléfono al que llegan los SMS** de los pacientes de ejemplo. En el `.env`:

   ```
   PRESENTACION_TELEFONO=7123-4567
   ```

   Si no se pone, los pacientes quedan con teléfonos fijos inventados y los recordatorios no llegan
   a nadie.

5. Para que los SMS lleguen de verdad, configurar Twilio (ver más abajo).

## Antes de cada presentación (el mismo día)

1. **Doble clic en `presentacion\preparar_datos.bat`** y escribir `s`. Borra la base de la
   presentación y la vuelve a crear con los datos de ejemplo. Las citas «de hoy» son del día en que
   se corre, por eso se hace el mismo día. Al terminar, los usuarios y la contraseña quedan en
   **`credenciales_presentacion.txt`** (en la carpeta del proyecto; no se sube a GitHub).
2. **Doble clic en `presentacion\encender.bat`**. Se abre otra ventana con el servidor y, en unos
   segundos, aparece la dirección pública, que termina en **`.trycloudflare.com`**.
3. Pasarle al profesor **la dirección** y **los usuarios** del archivo de credenciales.
4. Dejar la computadora **conectada a la corriente** y sin que se suspenda.

Para apagar todo: cerrar las dos ventanas.

## Qué hay en los datos de ejemplo

| Usuario | Rol | Para probar |
|---|---|---|
| `administrador` | Administrador | Reporte del mes, «Usuarios y roles», bitácora de accesos, panel de administración |
| `dra.lopez` y `dr.martinez` | Médico | Su agenda de hoy, el siguiente paciente con sus alergias, «Atender» y recetar |
| `recepcion` | Recepción | Registrar pacientes, agendar citas, entregar recetas e inventario |

- **14 pacientes** de todas las edades (3 menores con su responsable), con historial clínico.
- **Citas** de las últimas 5 semanas (atendidas, canceladas y «no asistió»), de hoy y de los
  próximos 7 días.
- **Consultas con receta.** Algunas recetas están **por entregar** en «Recetas» y otras se compran afuera.
- **Inventario** con 16 productos:
  - **Por vencer:** acetaminofén jarabe y amoxicilina suspensión.
  - **Vencido:** un lote de sales de rehidratación, para probar «Dar de baja».
  - **Bajo el mínimo:** jarabe, inhalador de salbutamol y jeringas.
  - **Historial:** compras, ventas, una donación y una merma.

Cosas que vale la pena enseñar:

- **Aviso de alergias:** María Elena Pérez es alérgica a la penicilina y Carlos Hernández al
  ibuprofeno. Al recetarle ibuprofeno a Carlos, el sistema avisa antes de guardar.
- **Recordatorio por SMS:** abrir una cita de mañana → **«Enviar recordatorio ahora»**. Con Twilio
  configurado, llega al celular de `PRESENTACION_TELEFONO`.
- **Recuperar lo escrito:** si la sesión se cierra por inactividad (30 minutos) mientras se atiende
  una consulta, al volver a entrar se recupera lo escrito.

## SMS de verdad con Twilio (cuenta de prueba, gratis)

1. Crear una cuenta en [twilio.com](https://www.twilio.com/try-twilio) y **verificar el número de
   celular** que va a recibir los mensajes (el mismo de `PRESENTACION_TELEFONO`).
2. En la página principal de la consola están el **Account SID**, el **Auth Token** y el
   **número de prueba** que Twilio asigna (empieza con +1).
3. **Permitir El Salvador:** Messaging → Settings → **Geo permissions** → marcar **El Salvador** →
   Save.
4. Agregar al `.env` (el Auth Token lo pega cada quien: **es secreto**, no lo pongan en el chat
   del grupo ni en GitHub):

   ```
   SMS_BACKEND=citas.sms.BackendTwilio
   TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   TWILIO_NUMERO=+1XXXXXXXXXX
   TWILIO_PLANTILLA_PRUEBA=sms_appointment_reminders
   ```

5. Cerrar y volver a abrir `encender.bat`.

Lo que hay que saber de la cuenta de prueba (así funciona desde 2026):

- **No acepta textos propios, solo plantillas de Twilio.** Por eso va `TWILIO_PLANTILLA_PRUEBA`:
  el SMS llega con el recordatorio de ejemplo de Twilio, en inglés y con una fecha inventada
  («Reminder: Appt Tue Oct 29, 3:00 PM…»). En la cita queda guardado nuestro texto en español.
  Con una cuenta pagada se borra esa línea y llega nuestro texto.
- **Solo manda a números verificados** y desde el número de prueba asignado. Si no, la cita
  muestra «Error al enviar» con el detalle que da Twilio.
- Con `SMS_BACKEND` en el `.env`, el sistema de trabajo también manda SMS de verdad, pero solo
  cuando se usa el botón o el comando `enviar_recordatorios`. Las pruebas (`manage.py test`)
  siempre usan el modo simulado.

Más detalles de los recordatorios en [recordatorios.md](recordatorios.md).

## Si algo falla

| Qué pasa | Qué hacer |
|---|---|
| «Falta instalar cloudflared» | Paso 1 de «Una sola vez». Después cierren y abran la ventana otra vez. |
| La ventana del servidor dice `SECRET_KEY` | Paso 3 de «Una sola vez». |
| La ventana del servidor dice que no se puede conectar con SQL Server | El servicio está apagado: Windows + R → `services.msc` → **SQL Server (SQLEXPRESS)** → Iniciar. |
| «Bad Request (400)» | Abran el sistema por la dirección `.trycloudflare.com` o por `http://127.0.0.1:8080`. |
| El enlace no abre | Revisen que las dos ventanas sigan abiertas y que haya internet. Si se cerraron, vuelvan a abrir `encender.bat` (el enlace cambia). |
| «Este usuario está bloqueado» | Se escribió mal la contraseña 5 veces: esperar 15 minutos o desbloquearlo como `administrador` en «Usuarios y roles». |
| Las citas de «hoy» son de otro día | Vuelvan a correr `preparar_datos.bat` (borra lo que se hizo en la presentación). |

## Cómo funciona (para el equipo)

- **`presentacion/encender.bat`:**
  - Pone `DB_NAME=clinica_presentacion`, `DEBUG=False`, `ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS`
    (`https://*.trycloudflare.com`) solo para esa ventana.
  - Enciende el sistema con **Waitress** en `127.0.0.1:8080`, que no se ve desde la red local.
  - Abre el enlace con `cloudflared tunnel --url`.
- **Sin el `.env` nada cambia:** `settings.py` lee `DEBUG`, `SECRET_KEY`, `ALLOWED_HOSTS` y
  `CSRF_TRUSTED_ORIGINS` del entorno. Sin ellos queda como siempre (DEBUG = True).
- **WhiteNoise** sirve el CSS cuando DEBUG = False.
- **`theme/templates/500.html`** es la página de error que se muestra en ese caso.
- **`manage.py preparar_presentacion`:**
  - Borra y crea la base. Solo acepta una base cuyo nombre tenga «presentacion».
  - Corre `migrate` y después `cargar_datos_de_ejemplo`.
- **`manage.py cargar_datos_de_ejemplo`:**
  - Carga los datos con las mismas funciones que usan las pantallas (`inventario.services`,
    `consultas.entregas`). Están en `consultas/datos_de_ejemplo.py`.
  - Se niega a correr si la base ya tiene pacientes.
  - Opciones: `--telefono` y `--clave`.
  - Pruebas en `consultas/tests_datos_de_ejemplo.py`.
