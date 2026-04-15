# Pulso Operativo

Dashboard de analytics operativo construido con Streamlit que consume datos de BambooHR para visualizar horas, costos y rentabilidad de proyectos.

## Tabs

| Tab | Descripcion |
|-----|-------------|
| **Overview** | KPIs generales, horas por semana, distribucion por proyecto |
| **Por Persona** | Detalle de horas y costo por colaborador |
| **Por Proyecto** | Horas, costo acumulado y tendencia por proyecto |
| **Por Departamento** | Comparativa entre departamentos |
| **Costos** | Costo por hora, burn rate, proyeccion mensual |
| **Asignaciones** | Matriz persona-proyecto con % de dedicacion |
| **Reporte** | Resumen semanal exportable a PDF |
| **Rentabilidad** | Seguimiento de margen por proyecto vs contrato |

## Setup

```bash
# Clonar e instalar dependencias
git clone https://github.com/aleistermi/pulso-operativo.git
cd pulso-operativo
pip install -r requirements.txt

# Configurar variables de entorno
cp .env.example .env
# Editar .env con tus credenciales
```

### Variables de entorno

| Variable | Descripcion |
|----------|-------------|
| `BAMBOOHR_API_KEY` | API key de BambooHR |
| `BAMBOOHR_SUBDOMAIN` | Subdominio de tu cuenta BambooHR |
| `APP_PASSWORD` | Password para acceder al dashboard |
| `ADMIN_PASSWORD` | Password para administrar proyectos (tab Rentabilidad) |

## Ejecucion

```bash
# Obtener datos frescos de BambooHR
python fetch_timesheets.py

# Levantar el dashboard
streamlit run dashboard.py
```

## Actualizacion automatica de datos

El script `update_data.sh` ejecuta `fetch_timesheets.py` y puede configurarse como cron job:

```bash
# Cada dia a las 8am
0 8 * * * /path/to/update_data.sh
```

## Deploy (Render)

El archivo `render.yaml` define el servicio. Configura las variables de entorno en el dashboard de Render.

## Stack

- **Streamlit** — UI y server
- **Plotly** — Graficas interactivas
- **Pandas** — Procesamiento de datos
- **fpdf2** — Generacion de reportes PDF
- **BambooHR API** — Fuente de datos de timesheets y salarios
- **Frankfurter API** — Tipos de cambio historicos
