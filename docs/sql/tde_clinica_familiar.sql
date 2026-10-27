/* ===========================================================================
   TDE (Transparent Data Encryption) para la base de datos clinica_familiar
   ---------------------------------------------------------------------------
   TDE cifra los ARCHIVOS de la base (.mdf, .ldf) y sus respaldos (.bak) con
   AES-256. Si alguien se roba el disco o un respaldo, no puede leer nada sin el
   certificado. El sistema (Django) no cambia: SQL Server cifra al escribir y
   descifra al leer.

   REQUISITOS
   - SQL Server Enterprise, Standard (2019 o más nuevo) o Developer.
     La edición Express NO permite TDE (el script se detiene si la detecta).
   - Ejecutarlo en SSMS conectado con un usuario administrador (sysadmin).

   ANTES DE EJECUTARLO
   1. Cambie las dos contraseñas marcadas con << >> por unas seguras.
   2. Cree la carpeta C:\RespaldosTDE (o cambie la ruta en el paso 3). La cuenta
      del servicio de SQL Server debe poder escribir en ella.
   3. Después, guarde los archivos .cer y .pvk y las contraseñas FUERA del
      servidor (por ejemplo, en un USB guardado bajo llave). Sin ellos, un
      respaldo de la base no se puede restaurar en otra computadora.
   =========================================================================== */

-- 0. Revisar que la edición permita TDE --------------------------------------
DECLARE @edicion nvarchar(128) = CAST(SERVERPROPERTY('Edition') AS nvarchar(128));
PRINT N'Edición de SQL Server: ' + @edicion;
IF @edicion LIKE N'Express%' OR @edicion LIKE N'Web%'
BEGIN
    RAISERROR(N'La edición %s no permite TDE. Use Standard, Enterprise o Developer.', 16, 1, @edicion);
    SET NOEXEC ON;  -- no ejecuta el resto del script
END
GO

USE master;
GO

-- 1. Clave maestra de la instancia (protege al certificado) -------------------
IF NOT EXISTS (SELECT 1 FROM sys.symmetric_keys WHERE name = N'##MS_DatabaseMasterKey##')
    CREATE MASTER KEY ENCRYPTION BY PASSWORD = N'<<Contraseña-segura-de-la-clave-maestra>>';
GO

-- 2. Certificado que protege la clave de la base -----------------------------
IF NOT EXISTS (SELECT 1 FROM sys.certificates WHERE name = N'CertificadoTDE_ClinicaFamiliar')
    CREATE CERTIFICATE CertificadoTDE_ClinicaFamiliar
        WITH SUBJECT = N'TDE - Clinica Familiar';
GO

-- 3. RESPALDO DEL CERTIFICADO (obligatorio) ----------------------------------
BACKUP CERTIFICATE CertificadoTDE_ClinicaFamiliar
    TO FILE = N'C:\RespaldosTDE\CertificadoTDE_ClinicaFamiliar.cer'
    WITH PRIVATE KEY (
        FILE = N'C:\RespaldosTDE\CertificadoTDE_ClinicaFamiliar.pvk',
        ENCRYPTION BY PASSWORD = N'<<Contraseña-segura-del-respaldo-del-certificado>>'
    );
GO

-- 4. Clave de cifrado de la base (AES de 256 bits) ---------------------------
USE clinica_familiar;
GO
IF NOT EXISTS (SELECT 1 FROM sys.dm_database_encryption_keys WHERE database_id = DB_ID())
    CREATE DATABASE ENCRYPTION KEY
        WITH ALGORITHM = AES_256
        ENCRYPTION BY SERVER CERTIFICATE CertificadoTDE_ClinicaFamiliar;
GO

-- 5. Activar el cifrado (SQL Server cifra la base en segundo plano) ----------
ALTER DATABASE clinica_familiar SET ENCRYPTION ON;
GO

-- 6. Verificar ---------------------------------------------------------------
SELECT
    DB_NAME(database_id) AS base_de_datos,
    encryption_state,
    CASE encryption_state
        WHEN 0 THEN N'Sin clave de cifrado'
        WHEN 1 THEN N'Sin cifrar'
        WHEN 2 THEN N'Cifrando...'
        WHEN 3 THEN N'CIFRADA'
        WHEN 4 THEN N'Cambiando la clave...'
        WHEN 5 THEN N'Descifrando...'
        WHEN 6 THEN N'Cambiando la protección...'
    END AS estado,
    percent_complete AS porcentaje,
    key_algorithm AS algoritmo,
    key_length AS bits
FROM sys.dm_database_encryption_keys;
-- La base clinica_familiar debe quedar en estado 3 (CIFRADA).
-- tempdb también aparece cifrada: SQL Server lo hace solo al activar TDE.
GO

SET NOEXEC OFF;
GO

/* ---------------------------------------------------------------------------
   PARA RESTAURAR UN RESPALDO EN OTRO SERVIDOR (que también permita TDE):
   USE master;
   CREATE MASTER KEY ENCRYPTION BY PASSWORD = N'<<otra contraseña>>';   -- si no tiene
   CREATE CERTIFICATE CertificadoTDE_ClinicaFamiliar
       FROM FILE = N'C:\RespaldosTDE\CertificadoTDE_ClinicaFamiliar.cer'
       WITH PRIVATE KEY (
           FILE = N'C:\RespaldosTDE\CertificadoTDE_ClinicaFamiliar.pvk',
           DECRYPTION BY PASSWORD = N'<<Contraseña-segura-del-respaldo-del-certificado>>'
       );
   -- y luego se restaura el .bak normalmente.

   PARA DESACTIVAR TDE:
   ALTER DATABASE clinica_familiar SET ENCRYPTION OFF;
   --------------------------------------------------------------------------- */
