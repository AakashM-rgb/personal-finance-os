/** Mirrors backend/app/schemas/auth.py's _validate_password_strength. A UX
 * convenience only - the backend is the authority and re-validates. */
export const PASSWORD_MIN_LENGTH = 8;
export const PASSWORD_MAX_LENGTH = 128;

export interface PasswordRule {
  label: string;
  isMet: boolean;
}

export function checkPasswordRules(password: string): PasswordRule[] {
  return [
    { label: `At least ${PASSWORD_MIN_LENGTH} characters`, isMet: password.length >= PASSWORD_MIN_LENGTH },
    { label: "Contains a letter", isMet: /[A-Za-z]/.test(password) },
    { label: "Contains a number", isMet: /\d/.test(password) },
  ];
}

export function isPasswordValid(password: string): boolean {
  return (
    password.length <= PASSWORD_MAX_LENGTH && checkPasswordRules(password).every((rule) => rule.isMet)
  );
}
