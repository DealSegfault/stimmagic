// Shared classifiers for LLM availability error codes returned by the backend
// as {detail: {code, message}}. They drive which remedy CTA a surface shows
// beside the error: add balance vs configure a chat model.

// "Signed in but no spendable balance" — current backend code plus legacy
// names still recognized as the same thing.
export function isInsufficientBalanceCode(code: string | null | undefined): boolean {
  return code === 'insufficient_balance' || code === 'llm_insufficient_balance'
    || code === 'subscription_required' || code === 'subscription_error'
}

// "No usable chat model" — the remedy is configuring one in
// Settings > Chat Models.
export function isLlmSetupCode(code: string | null | undefined): boolean {
  return code === 'llm_not_configured' || code === 'llm_not_logged_in'
    || code === 'llm_local_missing' || code === 'llm_model_missing'
    || code === 'llm_cloud_unreachable' || code === 'llm_provider_unavailable'
}
