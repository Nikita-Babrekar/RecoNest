// Replace your current firebase.js with this:
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.7.1/firebase-app-compat.js";
import { getAuth, GoogleAuthProvider } from "https://www.gstatic.com/firebasejs/10.7.1/firebase-auth-compat.js";

const firebaseConfig = {
  apiKey: "AIzaSyCVbzTMjEQweM4fmygqW4DvUtMPZggJmt0",
  authDomain: "reconest-42f2a.firebaseapp.com",
  projectId: "reconest-42f2a",
  storageBucket: "reconest-42f2a.appspot.com",
  messagingSenderId: "58481636991",
  appId: "1:58481636991:web:ae5d29204e9c45e990314a"
};

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const provider = new GoogleAuthProvider();

export { auth, provider };