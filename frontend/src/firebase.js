import { initializeApp } from "firebase/app";
import { getAnalytics } from "firebase/analytics";

// Your web app's Firebase configuration
const firebaseConfig = {
    apiKey: "AIzaSyAIY6BkbO6gRLMcLuOgtIBvwI4J1y2CHcw",
    authDomain: "aerial-episode-125308.firebaseapp.com",
    databaseURL: "https://aerial-episode-125308.firebaseio.com",
    projectId: "aerial-episode-125308",
    storageBucket: "aerial-episode-125308.appspot.com",
    messagingSenderId: "224314386927",
    appId: "1:224314386927:web:08bdead70144111af9ee1a",
    measurementId: "G-QYSB7BTCJ0"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
const analytics = getAnalytics(app);

export { app, analytics };
