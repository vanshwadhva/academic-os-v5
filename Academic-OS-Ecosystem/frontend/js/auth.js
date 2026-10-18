

import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js";
import {
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
  signOut,
  onAuthStateChanged
} from "https://www.gstatic.com/firebasejs/10.12.2/firebase-auth.js";

// Replace these values with the Firebase Web App configuration
// from your Firebase Console.
const firebaseConfig = {
  apiKey: "AIzaSyCTNPwLzpWNUI7ltQFJtv_E4W3oZQWnflQ",
  authDomain: "bits-dsai-tracker.firebaseapp.com",
  projectId: "bits-dsai-tracker",
  storageBucket: "bits-dsai-tracker.firebasestorage.app",
  messagingSenderId: "530627005818",
  appId: "1:530627005818:web:24ca6180f9ed9e2fcbdac3"
};

export const app = initializeApp(firebaseConfig);
export const auth = getAuth(app);
const provider = new GoogleAuthProvider();
localStorage.removeItem("firebaseToken");

export async function loginWithGoogle() {
  const result = await signInWithPopup(auth, provider);
  return result.user;
}

export async function logout() {
  await signOut(auth);
  localStorage.removeItem("firebaseToken");
}

export function subscribeAuth(callback) {
  return onAuthStateChanged(auth, callback);
}

export async function getFirebaseIdToken(forceRefresh = false) {
  const user = auth.currentUser;
  if (!user) {
    throw new Error("NOT_SIGNED_IN");
  }
  return user.getIdToken(forceRefresh);
}
