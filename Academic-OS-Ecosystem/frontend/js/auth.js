

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

export async function loginWithGoogle() {
  const result = await signInWithPopup(auth, provider);
  const user = result.user;

  const token = await user.getIdToken();
  localStorage.setItem("firebaseToken", token);

  return user;
}

export async function logout() {
  await signOut(auth);
  localStorage.removeItem("firebaseToken");
}

export function subscribeAuth(callback) {
  return onAuthStateChanged(auth, async (user) => {
    if (user) {
      const token = await user.getIdToken();
      localStorage.setItem("firebaseToken", token);
    } else {
      localStorage.removeItem("firebaseToken");
    }

    callback(user);
  });
}

export async function getFirebaseIdToken(forceRefresh = false) {
  const user = auth.currentUser;
  if (!user) {
    throw new Error("NOT_SIGNED_IN");
  }
  const token = await user.getIdToken(forceRefresh);
  localStorage.setItem("firebaseToken", token);
  return token;
}