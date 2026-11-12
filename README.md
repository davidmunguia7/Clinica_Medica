# Clínica Familiar · Sistema de gestión

[![Pruebas](https://github.com/davidmunguia7/Clinica_Medica/actions/workflows/pruebas.yml/badge.svg)](https://github.com/davidmunguia7/Clinica_Medica/actions/workflows/pruebas.yml)

Sistema web para una clínica familiar: pacientes, citas, inventario de medicamentos y reportes
en un solo lugar. Proyecto de equipo de Programación II.

## Módulos

| Módulo | Carpeta | Qué hace | Responsable |
|---|---|---|---|
| Usuarios y roles | `usuarios/` | Usuario con rol (Administrador, Médico, Recepción), permisos por rol, «Usuarios y roles» y «Mi perfil» | Adriana |
| Pacientes | `pacientes/` | Registro según la norma del MINSAL, expediente único, historial clínico | Fer |
| Inventario | `inventario/` | Productos, lotes con vencimiento, entradas y salidas, panel por categorías | David |
| Citas | `citas/` | Agenda por día y semana, estados de la cita, recordatorios por SMS | Por asignar |
| Consultas y recetas | `consultas/` | El médico atiende (consulta, diagnóstico y receta); Recepción entrega lo recetado y se descuenta del inventario | David |
| Reportes | `reportes/` | Reporte del mes: citas, pacientes, compras, ventas y ganancia | Por asignar |

Además:

- `sistema_clinico/`: configuración general (`settings.py`, `urls.py`), pantalla de inicio y el
  cifrado de datos (`cifrado.py`).
- `theme/`: diseño compartido. La plantilla base (`templates/base.html`), el login, la paleta de
  colores y los estilos de Tailwind.
- `docs/`: documentación de [seguridad (Fernet y TDE)](docs/seguridad.md) y de
  [recordatorios por SMS](docs/recordatorios.md).

## Tecnología

- **Python 3.13 o más nuevo** y **Django 6.1**
- **SQL Server Express**, con `mssql-django` y el **ODBC Driver 17 for SQL Server**
- **Tailwind CSS 4** con `django-tailwind`, en modo *standalone* (no necesita Node.js)
- `cryptography` (Fernet) para cifrar los datos sensibles de los pacientes

---

## Instalación (primera vez)

Todo se hace en una terminal de Windows (PowerShell), dentro de la carpeta del proyecto.

### 1. Descargar el proyecto y crear el entorno virtual

```powershell
git clone https://github.com/davidmunguia7/Clinica_Medica.git
cd Clinica_Medica
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 2. Crear el archivo `.env`

El `.env` guarda la configuración de **tu** computadora y **nunca se sube a GitHub**.

1. Copia `.env.example` y nómbralo `.env`.
2. En `DB_HOST` pon el nombre de tu servidor de SQL Server. Es el **"Server name"** que aparece
   en SSMS al conectarte, por ejemplo `MI-PC\SQLEXPRESS`.
3. Genera tu clave de cifrado (se escribe sola en el `.env`):

   ```powershell
   .\venv\Scripts\python.exe manage.py generar_clave_cifrado --guardar
   ```

   > ⚠️ **Guarda una copia del `.env` fuera de la computadora** (por ejemplo, en una USB). Sin la
   > `CLAVE_CIFRADO` no se pueden leer los datos cifrados de los pacientes.

| Variable | Para qué sirve |
|---|---|
| `DB_NAME` | Nombre de la base de datos (`clinica_familiar`) |
| `DB_HOST` | Servidor de SQL Server de tu computadora |
| `DB_USER`, `DB_PASSWORD` | Opcionales. Sin ellas se entra con tu cuenta de Windows (lo normal). |
| `CLAVE_CIFRADO` | Clave para cifrar los datos sensibles. Se genera con el comando del paso 3. |
| `CLINICA_TELEFONO` | Teléfono que aparece en los recordatorios por SMS |
| `SMS_BACKEND`, `TWILIO_*` | Solo para enviar SMS reales con Twilio (ver [docs/recordatorios.md](docs/recordatorios.md)) |

### 3. Crear la base de datos y las tablas

1. En SSMS: clic derecho en **Databases** > **New Database...** > nombre `clinica_familiar` > **OK**.
2. Crea las tablas y tu usuario administrador:

   ```powershell
   .\venv\Scripts\python.exe manage.py migrate
   .\venv\Scripts\python.exe manage.py createsuperuser
   ```

El orden importa: **primero la clave de cifrado, después `migrate`**.

---

## Correr el sistema

```powershell
.\venv\Scripts\python.exe manage.py runserver
```

Abre **http://127.0.0.1:8000/** y entra con tu usuario. Para apagarlo: `Ctrl + C` en la terminal.

- Usuarios y roles (solo Administrador): http://127.0.0.1:8000/cuentas/usuarios/
- Panel de administración (crear usuarios y asignarles su rol): http://127.0.0.1:8000/admin/
- Panel de inventario por categorías: http://127.0.0.1:8000/inventario/panel/

## Roles

Cada usuario tiene **un rol**, y el rol decide qué pantallas ve y qué puede hacer. Al entrar, cada
rol llega a **su propia pantalla de inicio**:

| Rol | Qué hace | Su pantalla de inicio |
|---|---|---|
| **Administrador** | Todo lo de Recepción, más leer las consultas, crear usuarios, asignar roles y entrar al panel de administración | Números del mes, el equipo con sus roles, citas de hoy y avisos del inventario |
| **Médico** | Atiende: consulta, diagnóstico y receta. Ve y actualiza expedientes y lleva su agenda. El inventario solo lo consulta; no registra pacientes nuevos | Solo **sus** citas, el siguiente paciente con sus **alergias** y el botón **Atender** |
| **Recepción** | Registra pacientes, maneja la agenda y el inventario y **entrega lo recetado** (ve la receta, no el diagnóstico) | Citas de hoy de todos los médicos, **recetas por entregar**, pacientes recién registrados y avisos del inventario |

## Consultas y recetas

1. **El médico atiende** con el botón «Atender» de la cita (o «Atender sin cita» en el expediente): anota
   motivo, síntomas, diagnóstico e indicaciones, y receta. Cada medicamento se elige **de la farmacia de
   la clínica** (se ve cuánto hay) o se escribe el nombre si el paciente lo **compra afuera**.
2. **Aviso de alergias:** si lo recetado coincide con las alergias del historial, el sistema avisa y pide
   confirmar antes de guardar.
3. Al guardar, la cita queda como «Atendida» y la consulta aparece en el expediente. La receta se puede
   **imprimir** (sin el diagnóstico).
4. **Recetar no descuenta nada.** Lo de la farmacia queda «por entregar» y **Recepción lo entrega** en
   «Recetas»: ahí se descuenta del inventario (primero el lote que vence antes, nunca uno vencido), como
   venta o sin costo, y la salida queda ligada al paciente. Si no alcanza, se deja pendiente o se marca
   que lo compra afuera.

La consulta, el diagnóstico y la receta se guardan **cifrados**, como el resto de los datos de salud.

- **Dónde se decide:** en `usuarios/roles.py` (`PERMISOS_POR_ROL`). Para darle o quitarle algo a
  un rol se cambia ese archivo y nada más; no hay que correr comandos.
- **Crear un usuario:** en el panel de administración → **Usuarios** → **Añadir**, y se elige su rol.
  Para que alguien deje de entrar, se le quita «Activo» (no se borra).
- **`createsuperuser`** crea usuarios con rol Administrador.
- La tabla completa de qué puede hacer cada rol está en la pantalla **Usuarios y roles**.
- **Pruebas:** si una prueba necesita un usuario *sin* los permisos de su rol, se marca con
  `@sin_permisos_de_rol()` (de `usuarios/pruebas.py`).

> Usamos `.\venv\Scripts\python.exe` para no tener que activar el entorno virtual. Si prefieres
> activarlo (`venv\Scripts\activate`), la línea debe empezar con `(venv)` y después basta con
> `python manage.py ...`.

## Después de cada `git pull`

Si alguien cambió dependencias o modelos, corre:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe manage.py migrate
```

---

## Cómo trabajamos

1. **Actualizar** antes de empezar: `git checkout main` y `git pull`.
2. **Rama propia**: `git checkout -b feature/<lo-que-vas-a-hacer>`. Nunca se trabaja directo en `main`.
3. **Trabajar solo en la carpeta de tu módulo.** Si necesitas tocar `settings.py`, `urls.py`,
   `base.html` o `requirements.txt`, avisa al grupo antes.
4. **Probar** antes de subir:

   ```powershell
   .\venv\Scripts\python.exe manage.py test
   ```

5. Si cambiaste clases de Tailwind en una plantilla, **recompila el CSS** y súbelo también:

   ```powershell
   .\venv\Scripts\python.exe manage.py tailwind build
   ```

6. **Pull Request** hacia `main`. Otro integrante lo revisa y lo aprueba.

### Pruebas automáticas en GitHub

Cada Pull Request corre solo las pruebas en GitHub (archivo
[`.github/workflows/pruebas.yml`](.github/workflows/pruebas.yml)), con un SQL Server de prueba:

1. revisa la configuración de Django,
2. revisa que no falten migraciones,
3. corre todas las pruebas,
4. revisa que el CSS compilado esté actualizado.

El resultado aparece en el PR: ✅ si todo pasa, ❌ si algo falla. Con **Details** se ve en qué paso
falló. **No fusionen un PR con ❌.**

### Estilos

Solo la paleta oficial (definida en `theme/static_src/src/styles.css`): `marino` (principal),
`verde-teal` (secundario), `coral` (acción principal, con texto oscuro), `blanco-humo` (fondo) y
`gris-oscuro` (texto). Reutilicen los componentes `btn`, `campo`, `tarjeta`, `insignia`, etc.

---

## Comandos útiles

| Comando | Para qué |
|---|---|
| `manage.py runserver` | Levanta el sistema en http://127.0.0.1:8000/ |
| `manage.py test` | Corre todas las pruebas (o `test inventario` para un solo módulo) |
| `manage.py createsuperuser` | Crea un usuario administrador |
| `manage.py changepassword <usuario>` | Cambia la contraseña de un usuario |
| `manage.py generar_clave_cifrado --guardar` | Crea la clave de cifrado en el `.env` |
| `manage.py recifrar_datos` | Vuelve a cifrar todo después de cambiar la clave |
| `manage.py enviar_recordatorios` | Envía (o simula) los SMS de las citas de las próximas 24 horas |
| `manage.py tailwind build` | Recompila el CSS |

(Todos se escriben después de `.\venv\Scripts\python.exe`).

## Problemas comunes

| Error | Solución |
|---|---|
| `No module named 'django'` | No estás usando el Python del entorno virtual. Usa `.\venv\Scripts\python.exe manage.py ...` |
| `That port is already in use` | Ya hay un servidor encendido en otra terminal. Ciérralo con `Ctrl + C`. |
| Error al conectar con SQL Server | Revisa `DB_HOST` en el `.env`. Si está bien, el servicio puede estar apagado: Windows + R → `services.msc` → **SQL Server (SQLEXPRESS)** → Iniciar. |
| `InconsistentMigrationHistory` al migrar | La base se creó antes del modelo de usuario. Borra la base en SSMS, créala vacía de nuevo y vuelve a correr `migrate`. |
| `No se pudo descifrar un dato guardado` | La `CLAVE_CIFRADO` del `.env` no es la misma con la que se cifraron los datos. Recupera la clave de tu copia. |
| Las pantallas se ven sin estilos | Corre `manage.py tailwind build`. |
