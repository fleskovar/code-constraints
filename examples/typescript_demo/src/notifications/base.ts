/** Notification senders. Abstract base + two concrete channels. */
export abstract class Notification {
  sender: string;

  constructor(sender: string) {
    this.sender = sender;
  }

  abstract send(to: string, message: string): boolean;
}

export class EmailNotifier extends Notification {
  smtpHost: string;

  constructor(sender: string = "noreply@bookstore.com") {
    super(sender);
    this.smtpHost = "localhost";
  }

  send(to: string, message: string): boolean {
    return to.includes("@");
  }
}

export class SmsNotifier extends Notification {
  shortCode: string;

  constructor(sender: string = "12345") {
    super(sender);
    this.shortCode = sender;
  }

  send(to: string, message: string): boolean {
    return message.length <= 160;
  }
}
