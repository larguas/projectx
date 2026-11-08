# Client TypeScript — génération depuis le schéma OpenAPI

Le contrat d'API est versionné dans le repo : **`backend/openapi.yaml`**.
Tout changement d'endpoint doit régénérer ce fichier (`make schema` dans
`backend/`) ; la CI échoue en cas de dérive non committée
(`make check` inclut `schema-check`).

Le frontend génère son client TypeScript depuis ce fichier avec
[openapi-typescript](https://openapi-ts.dev/openapi-typescript/) :

```bash
npm install -D openapi-typescript
```

```jsonc
// package.json (frontend)
{
  "scripts": {
    "generate:api": "openapi-typescript ../../backend/openapi.yaml -o src/api/schema.ts"
  }
}
```

Le fichier généré (`src/api/schema.ts`) expose :

- `components.schemas` : tous les schémas (modèles de réponses, `ErrorResponse`, …) ;
- `paths` : chaque opération avec ses paramètres et types de requête/réponse.

## Conventions du schéma à respecter côté backend

1. **`operationId` stables** : chaque vue déclare un `operation_id` explicite
   (`@extend_schema(operation_id=...)`). C'est le nom utilisé par le client
   généré ; ne pas le renommer sans migration.
2. **Enums nommés** : les champs à valeurs fermées utilisent
   `serializers.ChoiceField(choices=[...])` (ex. `HealthResponse.status`) pour
   que le schéma expose des enums typés et non de simples `string`.
3. **Réponses d'erreur typées** : tout le monde renvoie le même format,
   `ErrorResponse` (`{"error": {"code", "message", "details"}}`). Le schéma
   généré par `core.openapi.EMGAutoSchema` l'injecte automatiquement sur
   toutes les opérations. Les codes d'erreur stables sont définis dans
   `backend/core/exceptions.py`.

## Flux de travail

```text
backend :  make schema          # régénère openapi.yaml (à committer)
frontend : npm run generate:api # régénère src/api/schema.ts (à committer)
CI       :  make check          # échoue si openapi.yaml a dérivé
```
