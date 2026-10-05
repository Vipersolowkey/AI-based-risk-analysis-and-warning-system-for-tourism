// Web Push helpers: register the service worker, subscribe the browser to
// push notifications, and send the subscription to the backend.
import { apiGet, apiPost } from "./api";

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = atob(base64);
  return Uint8Array.from([...rawData].map((c) => c.charCodeAt(0)));
}

export function isPushSupported() {
  return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

export async function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) return null;
  return navigator.serviceWorker.register("/sw.js");
}

function subscriptionUsesKey(subscription, publicKey) {
  const expected = urlBase64ToUint8Array(publicKey);
  const current = new Uint8Array(subscription.options?.applicationServerKey || new ArrayBuffer(0));
  return current.length === expected.length
    && current.every((byte, index) => byte === expected[index]);
}

export async function getCurrentPushSubscription() {
  if (!isPushSupported()) return null;
  const registration = await navigator.serviceWorker.getRegistration("/");
  const subscription = registration ? await registration.pushManager.getSubscription() : null;
  if (!subscription) return null;
  const { publicKey } = await apiGet("/api/notifications/vapid-public-key");
  return publicKey && subscriptionUsesKey(subscription, publicKey) ? subscription : null;
}

/**
 * Requests Notification permission, subscribes to push, and registers the
 * subscription with the backend for the given watched destination.
 * Returns true on success, false if permission was denied or push isn't
 * supported/configured.
 */
export async function subscribeToPush(token, { destination, lat, lon } = {}) {
  if (!isPushSupported()) return false;

  const { publicKey } = await apiGet("/api/notifications/vapid-public-key");
  if (!publicKey) return false;
  const permission = await Notification.requestPermission();
  if (permission !== "granted") return false;

  const registration = await registerServiceWorker();
  if (!registration) return false;
  const applicationServerKey = urlBase64ToUint8Array(publicKey);
  let subscription = await registration.pushManager.getSubscription();
  if (subscription) {
    if (!subscriptionUsesKey(subscription, publicKey)) {
      await subscription.unsubscribe();
      subscription = null;
    }
  }
  if (!subscription) {
    subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey,
    });
  }
  const json = subscription.toJSON();

  await apiPost(
    "/api/notifications/subscribe",
    { endpoint: json.endpoint, keys: json.keys, destination, lat, lon },
    token
  );
  return true;
}

export async function unsubscribeFromPush(token) {
  const subscription = await getCurrentPushSubscription();
  if (!subscription) return false;
  await apiPost("/api/notifications/unsubscribe", { endpoint: subscription.endpoint }, token);
  await subscription.unsubscribe();
  return true;
}

export async function checkNow(token) {
  return apiPost("/api/notifications/check-now", {}, token);
}
