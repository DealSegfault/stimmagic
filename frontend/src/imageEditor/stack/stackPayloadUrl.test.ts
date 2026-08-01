import assert from 'node:assert/strict'
import test from 'node:test'
import { stackPayloadUrl } from './stackPayloadUrl.ts'

test('packaged payload URLs point directly at the sidecar with profile PIN auth', () => {
  assert.equal(
    stackPayloadUrl(
      'http://127.0.0.1:49152/api',
      3,
      'payloads/cand-42-patch.png',
      'profile-one',
      undefined,
      '12& 34',
    ),
    'http://127.0.0.1:49152/api/image-stack/3/payloads/cand-42-patch.png?subdir=payloads&profile=profile-one&pin=12%26+34',
  )
})

test('development payload URLs remain Vite-proxy relative and cache-bust revisions', () => {
  assert.equal(
    stackPayloadUrl('/api', 7, 'cache/head image.png', 'default', 9),
    '/api/image-stack/7/payloads/head%20image.png?subdir=cache&profile=default&revision=9',
  )
})
