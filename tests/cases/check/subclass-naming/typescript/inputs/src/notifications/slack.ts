import { Notification } from "./base";

// The violation: extends the base, name does not match /.*Notifier$/.
export class SlackHook extends Notification {
  send(message: string): void {}
}
