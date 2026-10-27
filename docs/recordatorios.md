# Recordatorios de cita por mensaje de texto (SMS)

Un día antes de cada cita, el sistema le manda al paciente un mensaje como este:

> Clínica Familiar: Hola Juan, le recordamos su cita el martes 14/10 a las 9:30 a. m. con
> Ana López. Si no puede asistir, llame al 2222-0000.

- A los **menores de edad** se les manda al teléfono del responsable.
- Cada mensaje queda guardado en la cita (sección «Recordatorios por mensaje de texto»), con el
  teléfono **cifrado**.
- Desde la cita también se puede mandar a mano con el botón **«Enviar recordatorio ahora»**.
- Si se cambia la hora de una cita, el recordatorio se vuelve a mandar.

## Por ahora los mensajes son simulados

Mientras no haya un proveedor de SMS contratado, el sistema **no manda nada**: el mensaje se
muestra en la terminal donde corre `runserver` y queda guardado como «Simulado». Así se puede
probar todo sin gastar dinero.

## Mandar los recordatorios del día

```
python manage.py enviar_recordatorios
```

Busca las citas programadas o confirmadas de las próximas 24 horas que todavía no tienen
recordatorio y manda uno a cada paciente. Opciones:

- `--horas 48` cambia la ventana de tiempo.
- `--simular` no manda nada aunque haya un proveedor configurado.

## Que se mande solo todos los días (Windows)

En el servidor de la clínica se programa con el **Programador de tareas** de Windows. Abran una
terminal (cmd) y peguen esto en **una sola línea**, cambiando `C:\ruta\Clinica_Medica` por la
carpeta del proyecto:

```
schtasks /Create /TN "Clinica Familiar - Recordatorios" /SC DAILY /ST 08:00 /TR "\"C:\ruta\Clinica_Medica\venv\Scripts\python.exe\" \"C:\ruta\Clinica_Medica\manage.py\" enviar_recordatorios"
```

Se ejecuta todos los días a las 8:00 a. m. Para probarlo sin esperar:
`schtasks /Run /TN "Clinica Familiar - Recordatorios"`. Para quitarlo:
`schtasks /Delete /TN "Clinica Familiar - Recordatorios"`.

## Mandarlos de verdad (Twilio)

1. Crear una cuenta en Twilio y comprar un número que pueda mandar SMS a El Salvador.
2. En el archivo `.env` agregar:

   ```
   SMS_BACKEND=citas.sms.BackendTwilio
   TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   TWILIO_NUMERO=+1XXXXXXXXXX
   CLINICA_TELEFONO=2222-0000
   ```

3. Reiniciar el servidor. Los teléfonos de 8 dígitos se envían con el código de El Salvador (+503).

Si Twilio responde con un error (saldo, número inválido, etc.), el mensaje queda como «Error al
enviar» con el detalle, y la cita sigue sin recordatorio para que se pueda volver a intentar.

**Código:** `citas/sms.py` (proveedores), `citas/recordatorios.py` (texto y envío) y
`citas/management/commands/enviar_recordatorios.py` (el comando). Para usar otro proveedor basta
con escribir una clase con el método `enviar(telefono, texto)` y ponerla en `SMS_BACKEND`.
