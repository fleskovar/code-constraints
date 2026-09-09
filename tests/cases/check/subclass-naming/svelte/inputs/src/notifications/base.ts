// Svelte projects keep logic in .ts modules; the Svelte parser reads them
// with the same TypeScript grammar, so class rules apply there too.
export abstract class Notification {
  abstract send(message: string): void;
}
