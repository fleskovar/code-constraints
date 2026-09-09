import { Notification } from "./base";

// Also breaks the pattern, but is named in `ignore:`.
export class LegacyPager extends Notification {
  send(message: string): void {}
}
