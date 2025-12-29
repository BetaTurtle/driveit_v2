import { initializeApp } from 'firebase/app';
import { getAuth } from 'firebase/auth';
import { getFirestore } from 'firebase/firestore';

const firebaseConfig = {
    apiKey: "AIzaSyAIY6BkbO6gRLMcLuOgtIBvwI4J1y2CHcw",
    authDomain: "aerial-episode-125308.firebaseapp.com",
    projectId: "aerial-episode-125308",
    appId: "1:224314386927:web:08bdead70144111af9ee1a"
};

export const app = initializeApp(firebaseConfig);
export const auth = getAuth(app);
export const db = getFirestore(app);

export const CONFIG = {
    auth: {
        backend: "https://driveit-v.deno.dev/authenticate",
        redirectUri: "https://betaturtle.github.io/driveit_v2/redir.html",
        clientId: "224314386927-kb90emu5vr086murg5ea0bmfod8tqlep.apps.googleusercontent.com"
    }
};
