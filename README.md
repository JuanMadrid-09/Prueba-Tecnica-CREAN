# Prueba Técnica CREAN — App de Inversiones

Solución para priorizar clientes con mayor propensión a adoptar la nueva app de inversiones y estimar el monto potencial a 12 meses.

---

## Ejecución

Requisitos: Python 3.9+, carpeta `02_Datos` con las bases SQLite.

**Datos:** el repo incluye los `.zip` en `02_Datos/`. Antes de ejecutar, descomprimelos ahí para obtener los `.db` (los `.db` no se suben a Git por su tamaño).

```bash
pip install -r requirements.txt
python construir_base_modelo.py
python modelo_adopcion.py
```

Los resultados quedan en `output/`. El tablero de Power BI usa `output/base_analitica_final.csv` (se genera al correr los scripts).

---

## Estructura del repositorio

```
Prueba-Tecnica-CREAN/
├── 01_Prueba/                # Enunciado de la prueba
├── 02_Datos/                 # Bases SQLite de clientes y productos
├── ecosistema_sqlite.py      # Conexion unificada a las 7 fuentes
├── construir_base_modelo.py  # Integracion, variables y score heuristico
├── modelo_adopcion.py        # Modelo ML complementario
├── output/                   # CSVs generados
├── requirements.txt
└── README.md
```

---

## 1. Planteamiento del problema

CREAN necesita lanzar una app de inversiones pero no tiene una visión integrada de:
- qué clientes tienen mayor probabilidad de adoptarla,
- cuánto podrían invertir en 12 meses,
- qué segmentos priorizar comercialmente.

La prueba es abierta: no hay una respuesta única ni parámetros obligatorios. Mi enfoque fue construir algo accionable, documentar supuestos y poder defender cada decisión.

---

## 2. Decisiones tomadas y por qué

### Integración de datos con SQLite ATTACH

**Decisión:** unificar las 7 fuentes en una sola conexión SQL con `ATTACH DATABASE`, granularidad a nivel `numero_id`.

**Por qué:**
- Es la llave común entre todas las tablas.
- Permite trazabilidad: cada variable se puede rastrear a su fuente.
- La transformación queda en SQL, no dispersa en varios scripts de pandas.

**Alternativa descartada:** leer cada `.db` por separado y hacer merges en pandas. Funciona, pero es más propenso a errores y difícil de mantener.

### Base analítica a nivel cliente

**Decisión:** una fila por cliente con agregaciones de productos (sum, avg, max, meses activos, último saldo).

**Por qué:** el negocio pregunta "¿qué clientes priorizar?", no "¿qué transacciones hubo?". Agregar por cliente es la granularidad correcta para segmentación y campañas.

### Variables derivadas

| Variable | Lógica | Por qué |
|---|---|---|
| `ingreso_disponible_mensual` | ingresos − egresos | Capacidad de ahorrar/invertir mes a mes |
| `riqueza_neta` | activos − pasivos | Capacidad patrimonial |
| `tiene_productos_inversion` | fiducuenta, CDT o invesbot | Señal directa de propensión inversionista |
| `tiene_productos_ahorro` | bolsillos o ahorro/corriente | Planeación financiera en no-inversionistas |
| Saldos recientes + meses activos | último corte y tracción temporal | Distingue cliente activo vs. uso puntual |

### Score heurístico de adopción

**Decisión:** score ponderado (0–1) con componentes escalados logarítmicamente al percentil 95.

**Componentes y pesos:**
- Ingreso disponible (28%)
- Riqueza neta (24%)
- Saldo actual en inversiones (18%)
- Meses de tracción en inversiones (12%)
- Estimador de ingresos (10%)
- Flag de productos de inversión (8%)

**Por qué heurístico y no solo ML:**
- Sin etiqueta real de adopción, necesito algo interpretable para negocio.
- Puedo explicar por qué un cliente puntúa alto.
- Es estable y no depende de un split train/test.

**Segmentación por percentiles:**
- Alta: percentil 95 (~5% de clientes)
- Media: percentil 80–95 (~15%)
- Baja: resto (~80%)

**Por qué percentiles:** la app no existe, no conozco la tasa real de adopción. Los percentiles garantizan una cola priorizable para lanzamiento por fases.

### Proxy de adopción para el ML

**Decisión:** definir un target proxy con dos perfiles:
1. **Inversionista activo:** tiene productos de inversión + tracción (meses, saldos).
2. **Prospecto alto:** sin inversión, pero con ahorro + ingreso y patrimonio en el top 20%.

**Por qué:** no hay histórico de adopción de la app. El proxy usa comportamiento observable como mejor aproximación. Cuando exista adopción real, se reentrena con etiqueta verdadera.

### Modelo ML sin leakage

**Decisión:** entrenar Random Forest y Regresión Logística excluyendo del ML las variables que componen el target proxy (saldos de inversión, patrimonio directo, flags de productos de inversión).

**Por qué:** si el modelo ve las mismas señales con las que definí el target, el AUC sube artificialmente (~0.99) sin aportar valor. Excluyendo esas variables, el AUC baja a ~0.91, que es más creíble.

**Features que sí usa el ML:** demografía, estimador de ingresos, métricas de bolsillos y ahorro/corriente.

**Mejor modelo:** Random Forest (AUC-ROC 0.91, precision@top10 0.93).

### Estimación de monto potencial 12 meses

**Decisión:** combinar tres fuentes de capacidad:
- 15% del ingreso anual disponible
- 1.5% de la riqueza neta
- 6% del saldo actual en inversiones

Modulado por el score de adopción: `monto = base × (0.40 + 0.60 × score)`.

**Tope p99:** evita que outliers distorsionen totales agregados.

**Escenario conservador (30%):** para planeación prudente. Los montos son estimaciones de **priorización comercial**, no proyección contable.

### Power BI como capa de visualización

**Decisión:** procesamiento en Python, consumo en Power BI.

**Por qué:** Python integra bien las fuentes y permite documentar la lógica analítica. Power BI es la herramienta natural para que negocio explore segmentos, filtros y tops de clientes. Separar ambas capas es coherente con cómo se opera en la práctica.

---

## 3. Resultados principales

### Universo analizado
- **860.223** clientes
- **25,6%** con productos de inversión (CDT, Fiducuenta o Invesbot)
- **0,6%** usa Invesbot (nicho digital)
- **~50%** de IDs en negativo por tamaño del identificador 64-bit (se trataron como texto, no afecta joins)

### Segmentación heurística

| Segmento | Clientes | % | Score prom. | Monto conservador 12M |
|---|---|---|---|---|
| Alta | 43.012 | ~5% | 0,97 | ~253 MM |
| Media | 129.033 | ~15% | 0,86 | ~415 MM |
| Baja | 688.178 | ~80% | 0,47 | ~650 MM |

### Modelo ML (Random Forest)
- AUC-ROC: **0,91**
- Precision@top10: **0,93**
- Prevalencia del proxy: **27%**

### Lectura de negocio
- El segmento **Alta** concentra clientes con mayor capacidad financiera e historial inversionista → foco comercial inicial.
- El segmento **Media** son candidatos a nurturing y educación financiera.
- El segmento **Baja** se aborda con activación digital de bajo costo.
- **Invesbot** es un nicho pequeño pero relevante: señal de adopción digital previa.
- El segmento comercial **preferencial** concentra la mayor proporción de clientes Alta.

---

## 4. Supuestos explícitos

1. No existe etiqueta histórica de adopción de la nueva app.
2. El proxy de adopción se basa en comportamiento inversionista observable.
3. Los montos son para priorización comercial, no contabilidad.
4. `numero_id` es llave válida a pesar de valores negativos (identificadores 64-bit).
5. Los pesos del score heurístico son iniciales y se recalibrarían con datos post-lanzamiento.

---

## 5. Operación en CREAN

| Proceso CREAN | Cómo aporta la solución |
|---|---|
| Administrar información | Base analítica mensual recalculable desde las fuentes |
| Afiliar / Desafiliar | Listas priorizadas (`top_clientes_ml.csv`) para campañas |
| Monitorear servicio | KPIs: adopción por segmento, monto captado vs. estimado |
| Gestionar uso del servicio | Activación por fases: Alta → Media → Baja |

**Frecuencia sugerida:** recálculo mensual con corte de saldos y clientes.

**Evolución:** cuando exista adopción real de la app, reemplazar el target proxy por etiqueta observada y recalibrar montos con datos de conversión.

---

## 6. Archivos generados

| Archivo | Contenido |
|---|---|
| `base_analitica_cliente.csv` | Base integrada + score heurístico |
| `base_analitica_final.csv` | Base + probabilidades ML (input de Power BI) |
| `resumen_segmentos.csv` | Dimensionamiento por segmento heurístico |
| `resumen_segmentos_ml.csv` | Dimensionamiento por segmento ML |
| `modelo_metricas.csv` | Comparación Logistic vs Random Forest |
| `top_clientes_ml.csv` | Top 20.000 clientes priorizados |

---

## 7. Limitaciones y mejoras futuras

- El proxy de adopción no es conversión real; se valida con piloto post-lanzamiento.
- Los montos agregados son elevados; usarlos como ranking relativo, no cifra contable.
- No se aplicaron filtros de elegibilidad (edad, restricciones regulatorias); se pueden agregar como capa previa al scoring.
- Con más tiempo: validar pesos con negocio, piloto A/B por segmento, integración a CRM.
