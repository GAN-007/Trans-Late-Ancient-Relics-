export async function request(url, options = {}) {
  const response = await fetch(url, {
    credentials: 'same-origin',
    ...options,
    headers: {
      ...(options.body ? {'Content-Type': 'application/json'} : {}),
      ...(options.headers || {}),
    },
  });
  let payload = null;
  const contentType = response.headers.get('content-type') || '';
  try {
    payload = contentType.includes('application/json') ? await response.json() : await response.text();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const message = payload?.detail || payload?.message || (typeof payload === 'string' ? payload : `HTTP ${response.status}`);
    throw new Error(message);
  }
  return payload;
}

export const get = url => request(url);
export const post = (url, body) => request(url, {method:'POST', body:JSON.stringify(body)});
export const put = (url, body) => request(url, {method:'PUT', body:JSON.stringify(body)});
export const del = url => request(url, {method:'DELETE'});
