# Ontología Epistémica del Motor Socrático

## La Separación Fundamental

Este motor implementa una distinción crítica que la mayoría de frameworks ignoran:

- **Truth** (verdad lógica): ¿La proposición es verdadera bajo las reglas del sistema?
- **Certification** (certificación): ¿Tenemos evidencia estructural suficiente para afirmar esto?

Ejemplo:
- Un LLM dice "el servicio está corriendo" → `truth=TRUE, certified=FALSE` (opinión)
- `pgrep` verifica el proceso → `truth=TRUE, certified=TRUE` (evidencia)
- El servicio no existe → `truth=FALSE, certified=TRUE` (evidencia de ausencia)

## Lógica Trivaluada

El motor usa tres valores, no dos:

- **TRUE**: La proposición es verdadera Y está certificada con evidencia
- **FALSE**: La proposición es falsa Y hay evidencia estructural de ello
- **UNKNOWN**: No hay evidencia suficiente para decidir (R9: sin concesiones silenciosas)

### ¿Por qué UNKNOWN es crítico?

En sistemas de certificación, la ausencia de evidencia NO es falsedad. Es indeterminación.
Si un predicado no puede verificar algo (timeout, servicio caído, datos faltantes),
retornar FALSE sería una mentira. UNKNOWN es la respuesta honesta.

## Reglas de Certificación por Operador

La certificación se propaga recursivamente según reglas específicas:

| Operador | Certificación requiere |
|----------|----------------------|
| AND | Todos los hijos certificados |
| OR | Al menos un hijo TRUE certificado |
| NOT | El hijo certificado |
| XOR | Ambos hijos certificados |
| IMPLIES | Antecedente Y consecuente certificados |
| DIALECTICAL_AND | En conflicto: TODOS los hijos certificados (la contradicción misma es un hecho); sin conflicto: todos los hijos certificados |

Esto garantiza que una certificación compuesta solo sea TRUE si TODAS las partes
relevantes tienen evidencia estructural.

## Operador Dialéctico (DIALECTICAL_AND)

La dialéctica hegeliana aplicada a la certificación: **tesis + antítesis → síntesis**.

Un AND normal cortocircuita a FALSE ante cualquier hijo FALSE — una contradicción
es un rechazo. Pero hay contradicciones **legítimas**: dos afirmaciones opuestas,
AMBAS con evidencia estructural certificada (p.ej. un servicio dice "arriba" y un
healthcheck externo dice "caído"). Rechazar es tomar partido por la antítesis;
aprobar es tomar partido por la tesis. Ambas serían una concesión silenciosa.

`DIALECTICAL_AND` trata la contradicción certificada como **indeterminación
productiva**:

- Todos los hijos TRUE → `TRUE` certificado (sin tensión)
- Todos los hijos FALSE → `FALSE` certificado (sin tensión)
- Mezcla TRUE/FALSE, TODOS certificados → `UNKNOWN` **certificado**, con
  `metadata.dialectical_conflict=true` y la tesis/antítesis documentadas con su
  evidencia (qué hijos afirman, cuáles niegan)
- Mezcla TRUE/FALSE con algún hijo NO certificado → `UNKNOWN` no certificado
  (falta de evidencia, no tensión establecida)

El `UNKNOWN` certificado es distinto del `UNKNOWN` ordinario: no es "no hay
evidencia", es "hay evidencia en conflicto". El nivel superior debe **sintetizar**
— el resultado conserva la tensión completa en metadata para que esa síntesis sea
posible sin perder información.

El diagnóstico (`diagnose()`) NO señala hijos culpables en un conflicto
certificado: apuntar a un hijo sería tomar partido por la tesis o la antítesis.
La contradicción misma es el estado a resolver en el nivel superior.

## El Papel del LLM (R10)

El LLM puede:
- ✅ Proponer árboles de cuestionamiento (generar IR)
- ✅ Opinar en predicados (`llm_judge`)
- ❌ NUNCA certificar (`certified=True`)

La certificación requiere evidencia determinista, verificable, auditable.
El LLM es una fuente de hipótesis, no de verdades.

## Trace Inverso: Diagnóstico de Fallos

Cuando un árbol no se certifica, el motor no solo dice "FALSE".
Proporciona un **trace inverso** que identifica exactamente qué hojas fallaron:

```
op:AND → false [✗]
  service_running → true [✓]
  schema_valid → true [✓]
  llm_judge → true [✗]  ← Este falló la certificación
```

Esto convierte "no pasó" en "falló aquí, por esta razón, con esta evidencia".

## Analogía con Lógica Cuántica

El motor implementa una estructura similar a la lógica cuántica:
- Proposiciones sin valor definido pre-medición → UNKNOWN
- Medición (invocación de predicado) → colapso a TRUE/FALSE
- Contexto de evaluación → preservado en cada Evaluation

La diferencia: aquí la "medición" es verificación estructural, no física.
Pero la estructura matemática es análoga.

## Relación con VSM (Viable System Model)

Este motor es una instancia de los sistemas epistémicos requeridos por VSM:
- **S1** (operaciones): predicados verifican claims contra realidad
- **S3** (control): state-canon reconcilia estado declarado vs observado
- **S3*** (auditoría): verify_boot_ontology verifica los verificadores

El motor es agnóstico al dominio, pero su arquitectura respeta la topología VSM.

## Casos de Uso

1. **Gates de CI/CD**: Verificar que un deploy es seguro antes de ejecutarlo
2. **Validación de documentos**: Certificar que un spec cumple reglas estructurales
3. **Decisión ética**: Requerir consentimiento de stakeholders antes de acciones críticas
4. **Diagnóstico de fallos**: Identificar exactamente qué parte de un sistema falló

## Lo que este motor NO es

- ❌ No es un framework de agentes (LangChain, AutoGen)
- ❌ No es una base de datos vectorial (Pinecone, Weaviate)
- ❌ No es un sistema de prompting (DSPy, Guardrails)
- ❌ No hace al LLM más inteligente

Es **infraestructura de verificación** que hace a los agentes confiables.
