// The base extends nothing, so the rule never examines its name.
export abstract class Notification {
  abstract send(message: string): void;
}
