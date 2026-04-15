# Guia de deploy - Pulso Operativo

Esta guia es para que el equipo pueda desplegar y mantener el dashboard de forma independiente.

## Requisitos previos

1. **Cuenta de GitHub** con acceso al repo `pulso-operativo`
2. **Cuenta en un servicio de hosting** (Render, Railway, o similar)
3. **Credenciales de BambooHR**:
   - API Key (se genera en BambooHR > Account > API Keys)
   - Subdomain (es la parte antes de `.bamboohr.com` en la URL de su cuenta)
4. **Passwords del dashboard**:
   - `APP_PASSWORD` — password para entrar al dashboard
   - `ADMIN_PASSWORD` — password para administrar proyectos en la tab Rentabilidad

---

## Opcion 1: Deploy en Render (recomendado)

### Paso 1: Crear cuenta en Render
- Ir a [render.com](https://render.com) y crear una cuenta (puede ser con GitHub)

### Paso 2: Conectar GitHub
- En Render, ir a **Dashboard > New > Web Service**
- Seleccionar **"Connect GitHub"** y autorizar acceso al repo `pulso-operativo`
- Si el repo no aparece, ir a GitHub > Settings > Applications > Render > Configure, y agregar el repo

### Paso 3: Configurar el servicio
- **Name**: `pulso-operativo` (o el nombre que quieran)
- **Branch**: `main`
- **Runtime**: Python
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `streamlit run dashboard.py --server.port $PORT --server.address 0.0.0.0 --server.headless true`
- **Plan**: Free (suficiente para uso interno; el servicio se duerme tras 15 min de inactividad)

### Paso 4: Variables de entorno
En la seccion **Environment > Environment Variables**, agregar:

| Key | Value |
|-----|-------|
| `BAMBOOHR_API_KEY` | (su API key de BambooHR) |
| `BAMBOOHR_SUBDOMAIN` | (su subdominio, ej: `entropia`) |
| `APP_PASSWORD` | (password para usuarios del dashboard) |
| `ADMIN_PASSWORD` | (password para administrar proyectos) |

### Paso 5: Deploy
- Hacer clic en **Create Web Service**
- El build tarda 2-3 minutos. La URL sera algo como `https://pulso-operativo.onrender.com`

### Notas sobre Render Free
- El servicio se duerme tras 15 min sin trafico. La primera visita despues de dormir tarda ~30 segundos en despertar.
- Si necesitan que este siempre activo, cambiar al plan Starter ($7/mes).

---

## Opcion 2: Deploy en Railway

### Paso 1: Crear cuenta
- Ir a [railway.app](https://railway.app) y entrar con GitHub

### Paso 2: Crear proyecto
- **New Project > Deploy from GitHub repo** > seleccionar `pulso-operativo`

### Paso 3: Configurar
- En **Settings > Deploy**:
  - Build Command: `pip install -r requirements.txt`
  - Start Command: `streamlit run dashboard.py --server.port $PORT --server.address 0.0.0.0 --server.headless true`
- En **Variables**, agregar las mismas 4 variables de entorno

### Paso 4: Generar dominio
- En **Settings > Networking > Generate Domain**

---

## Opcion 3: Correr en un servidor propio

```bash
# Clonar el repo
git clone https://github.com/aleistermi/pulso-operativo.git
cd pulso-operativo

# Crear entorno virtual
python3 -m venv venv
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt

# Configurar variables
cp .env.example .env
# Editar .env con las credenciales reales

# Obtener datos de BambooHR
python fetch_timesheets.py

# Levantar el dashboard
streamlit run dashboard.py --server.port 8501 --server.address 0.0.0.0 --server.headless true
```

Para mantenerlo corriendo en background, usar `nohup`, `screen`, `tmux`, o `systemd`.

---

## Actualizacion de datos

Los datos de BambooHR se cachean localmente en la carpeta `data/`. Para actualizar:

### Manual
```bash
python fetch_timesheets.py
```

### Automatica (cron)
El script `update_data.sh` ejecuta el fetch. Configurar un cron job:

```bash
crontab -e
# Agregar:
0 8 * * * /ruta/completa/update_data.sh
```

En Render/Railway, los datos se actualizan cada vez que un usuario abre el dashboard (cache de 1 hora en Streamlit).

---

## Administracion de proyectos (Rentabilidad)

La tab **Rentabilidad** permite configurar contratos y dar seguimiento al margen por proyecto.

- Para administrar: entrar con `ADMIN_PASSWORD` en la seccion "Administrar proyectos"
- Los datos de proyectos se guardan en `data/projects.json`
- **Este archivo no esta en git** (contiene datos financieros). Si se redeploya desde cero, hay que reconfigurarlo manualmente o restaurar el archivo desde un backup.

### Backup de projects.json
Es importante hacer backup periodico de `data/projects.json`. Este archivo contiene toda la configuracion financiera de los proyectos (contratos, estimaciones, hitos de pago).

---

## Transferencia del repo

Si necesitan mover el repo a otra cuenta/organizacion de GitHub:

1. En GitHub > Settings del repo > Transfer ownership
2. Actualizar la conexion en Render/Railway con el nuevo repo
3. Actualizar las env vars si cambiaron credenciales

---

## Troubleshooting

| Problema | Solucion |
|----------|----------|
| "No hay datos" al abrir | Ejecutar `python fetch_timesheets.py` o esperar a que el cache se actualice |
| Error de autenticacion BambooHR | Verificar `BAMBOOHR_API_KEY` y `BAMBOOHR_SUBDOMAIN` en env vars |
| La app no carga en Render | Revisar logs en Render Dashboard > Logs |
| Tab Rentabilidad sin datos | Entrar como admin y configurar los proyectos |
| El deploy falla en build | Verificar que `requirements.txt` no tenga versiones incompatibles |
