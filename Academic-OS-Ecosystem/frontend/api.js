const API_URL = "https://academic-os-api.onrender.com";

async function testBackend() {
    const response = await fetch(`${API_URL}/health`);
    const data = await response.json();
    console.log(data);
}

testBackend();