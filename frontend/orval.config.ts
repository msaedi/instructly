import { defineConfig } from 'orval';

export default defineConfig({
  instructly: {
    input: {
      target: '../backend/openapi/openapi.json',
    },
    output: {
      target: 'src/api/generated/instructly.ts',
      client: 'react-query',
      mode: 'tags-split',
      override: {
        mutator: {
          path: 'src/api/orval-mutator.ts',
          name: 'customFetch',
        },
        query: {
          useQuery: true,
          useMutation: true,
          signal: true,
        },
        fetch: {
          // Return the defined response type instead of wrapped {data, status, headers}
          includeHttpResponseReturnType: false,
        },
      },
    },
  },
});
