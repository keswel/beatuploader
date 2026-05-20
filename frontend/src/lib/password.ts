// Mirror of backend/app/schemas/user._validate_password.
// Keep these two in sync by hand — same rules, same messages.

export const PASSWORD_MIN_LENGTH = 8;
export const PASSWORD_MAX_LENGTH = 128;

export interface PasswordChecks {
  length: boolean;
  upper: boolean;
  lower: boolean;
  digit: boolean;
  special: boolean;
}

const SPECIAL_RE = /[!@#$%^&*()\-_=+[\]{};:,.<>/?\\|`~'"]/;

export function checkPassword(value: string): PasswordChecks {
  return {
    length: value.length >= PASSWORD_MIN_LENGTH && value.length <= PASSWORD_MAX_LENGTH,
    upper: /[A-Z]/.test(value),
    lower: /[a-z]/.test(value),
    digit: /[0-9]/.test(value),
    special: SPECIAL_RE.test(value),
  };
}

export function isPasswordValid(value: string): boolean {
  const c = checkPassword(value);
  return c.length && c.upper && c.lower && c.digit && c.special;
}
