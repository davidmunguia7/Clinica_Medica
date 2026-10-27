# Seguridad de los datos: Fernet y TDE

El sistema protege los datos de los pacientes con dos capas que se complementan:

| | **Fernet** (en la aplicación) | **TDE** (en SQL Server) |
|---|---|---|
| Qué cifra | Campos sensibles, uno por uno | Toda la base: archivos `.mdf`, `.ldf` y respaldos `.bak` |
| Quién lo hace | Django, al guardar | SQL Server, al escribir en disco |
| Protege contra | Alguien que entra a SQL Server o ve las tablas en SSMS | Robo del disco, de la computadora o de un respaldo |
| No protege contra | Robo de la clave del `.env` | Alguien con acceso a SQL Server (ve los datos en claro) |
| Dónde está la clave | `CLAVE_CIFRADO` en el `.env` de cada computadora | Certificado guardado en SQL Server (con respaldo aparte) |

Por eso se usan las dos: TDE cubre el disco y los respaldos, y Fernet cubre los datos más
delicados aunque alguien tenga acceso a la base.

---

## 1. Fernet (biblioteca `cryptography`)

Fernet cifra con AES-128 (modo CBC) y firma con HMAC-SHA256, así que también detecta si alguien
modificó un dato a mano. El mismo texto se cifra distinto cada vez, por lo que en la tabla no se
puede saber si dos pacientes tienen el mismo teléfono.

**Código:** `sistema_clinico/cifrado.py` (el campo `CampoCifrado` se puede usar en cualquier módulo).

### Qué está cifrado

- **Paciente:** número de documento, dirección, punto de referencia, teléfonos, correo, número de
  afiliación, nombres de madre y padre, datos del responsable (nombre, DUI, teléfono), quién dio los
  datos y observaciones.
- **Historial clínico:** tipo de sangre, alergias, enfermedades crónicas, medicamentos y antecedentes.
- **Citas:** motivo de la consulta y notas internas; de cada recordatorio por SMS, el teléfono y el texto.

**Sin cifrar, a propósito:** nombres y apellidos, fecha de nacimiento, sexo, distrito y número de
expediente. Se necesitan para buscar, ordenar la lista y detectar expedientes duplicados; un dato
cifrado no se puede buscar ni ordenar.

### Buscar por documento sin guardarlo en claro

Además del documento cifrado se guarda su **huella** (`documento_huella`, HMAC-SHA256). La huella es
siempre igual para el mismo documento, pero no permite recuperar el número. Con ella el sistema:

- encuentra a un paciente cuando se escribe su DUI completo en el buscador (con o sin guion), y
- no deja registrar dos veces el mismo documento.

### La clave

Cada computadora pone su clave en el archivo `.env` (que no se sube a GitHub):

```
python manage.py generar_clave_cifrado --guardar
```

- **Guarde una copia de la clave fuera de la computadora.** Si se pierde, los datos cifrados no se
  pueden recuperar.
- En desarrollo, si falta la clave, se usa una de prueba derivada de `SECRET_KEY` y Django muestra el
  aviso `pacientes.W001`. En producción (`DEBUG = False`) el sistema no arranca sin clave.
- Si ya tenía pacientes registrados antes de poner la clave, corra después
  `python manage.py recifrar_datos`.

### Cambiar la clave

1. Genere una nueva con `python manage.py generar_clave_cifrado`.
2. En el `.env` ponga la nueva primero y la anterior después, separadas por coma:
   `CLAVE_CIFRADO=clave_nueva,clave_anterior`
3. Corra `python manage.py recifrar_datos` (vuelve a cifrar todo con la nueva —pacientes, historiales,
   citas y mensajes— y recalcula las huellas).
4. Quite la clave anterior del `.env`.

---

## 2. TDE (Transparent Data Encryption)

**Script:** `docs/sql/tde_clinica_familiar.sql` (se abre y ejecuta en SSMS).

TDE requiere SQL Server **Enterprise, Standard o Developer**. La edición **Express no lo permite**,
así que en las computadoras del equipo (que usan Express) no se activa: el script lo detecta y se
detiene. Se activa en el servidor real de la clínica, o para demostrarlo se puede instalar SQL Server
Developer, que es gratis.

Pasos del script:

1. Crea la clave maestra de la instancia.
2. Crea el certificado `CertificadoTDE_ClinicaFamiliar`.
3. **Respalda el certificado** en `C:\RespaldosTDE` (sin ese respaldo, un `.bak` de la base no se puede
   restaurar en otro servidor).
4. Crea la clave de cifrado de la base con AES-256.
5. Activa el cifrado y muestra el estado (debe quedar en **3 = CIFRADA**).

El sistema en Django no necesita ningún cambio para usar TDE.

---

## Fuentes

- Microsoft, *Editions and supported features of SQL Server 2022* (tabla de seguridad: TDE en
  Enterprise y Standard, no en Express): https://learn.microsoft.com/sql/sql-server/editions-and-components-of-sql-server-2022
- Microsoft, *Transparent data encryption (TDE)*: https://learn.microsoft.com/sql/relational-databases/security/encryption/transparent-data-encryption
- Documentación de `cryptography`, *Fernet (symmetric encryption)*: https://cryptography.io/en/latest/fernet/
