// Privacy and legal page script (extracted from the page for the extension CSP).
  // ---------- FIREBASE AUTH GUARD ----------
  const firebaseConfig = {
    apiKey: "AIzaSyCTNPwLzpWNUI7ltQFJtv_E4W3oZQWnflQ",
    authDomain: "bits-dsai-tracker.firebaseapp.com",
    projectId: "bits-dsai-tracker",
    storageBucket: "bits-dsai-tracker.firebasestorage.app",
    messagingSenderId: "530627005818",
    appId: "1:530627005818:web:24ca6180f9ed9e2fcbdac3",
    measurementId: "G-LQWPPG78GS"
  };

  firebase.initializeApp(firebaseConfig);
  const auth = firebase.auth();

  auth.onAuthStateChanged(async (user) => {
    if (!user) {
      window.location.href = "login.html";
      return;
    }

    const email = user.email || "";

    if (!email.endsWith("@bitspilani-digital.edu.in")) {
      await auth.signOut();
      alert("Only BITS Pilani Digital accounts can use this application.");
      window.location.href = "login.html";
      return;
    }
  });

  function logoutUser() {
    auth.signOut().then(() => {
      window.location.href = "login.html";
    });
  }

  // ---------- PORTAL CONTROLLERS ----------
  const tabPrivacy = document.getElementById('tabPrivacy');
  const tabTerms = document.getElementById('tabTerms');
  const privacyPolicy = document.getElementById('privacyPolicy');
  const termsConditions = document.getElementById('termsConditions');
  const privacySidebar = document.getElementById('privacySidebar');
  const termsSidebar = document.getElementById('termsSidebar');

  // Tab Toggle Logic
  function selectTab(tab) {
    if (tab === 'privacy') {
      tabPrivacy.classList.add('active');
      tabTerms.classList.remove('active');
      privacyPolicy.classList.remove('hidden');
      termsConditions.classList.add('hidden');
      privacySidebar.classList.remove('hidden');
      termsSidebar.classList.add('hidden');
      
      // Select first sidebar element
      updateActiveSidebarItem(privacySidebar.querySelector('.nav-item'));
    } else {
      tabTerms.classList.add('active');
      tabPrivacy.classList.remove('active');
      termsConditions.classList.remove('hidden');
      privacyPolicy.classList.add('hidden');
      termsSidebar.classList.remove('hidden');
      privacySidebar.classList.add('hidden');
      
      // Select first sidebar element
      updateActiveSidebarItem(termsSidebar.querySelector('.nav-item'));
    }
  }

  tabPrivacy.addEventListener('click', () => selectTab('privacy'));
  tabTerms.addEventListener('click', () => selectTab('terms'));

  // Sidebar Link Active Highlight Loop
  const navItems = document.querySelectorAll('.nav-item');
  function updateActiveSidebarItem(target) {
    navItems.forEach(item => item.classList.remove('active'));
    target.classList.add('active');
  }

  navItems.forEach(item => {
    item.addEventListener('click', (e) => {
      updateActiveSidebarItem(e.currentTarget);
    });
  });

  // ---------- DOCUMENT SEARCH ENGINE ----------
  const searchInput = document.getElementById('legalSearch');
  searchInput.addEventListener('input', (e) => {
    const term = e.target.value.toLowerCase().trim();
    const sections = document.querySelectorAll('.policy-section');
    
    sections.forEach(section => {
      const text = section.innerText.toLowerCase();
      if (text.includes(term)) {
        section.style.display = 'block';
      } else {
        section.style.display = 'none';
      }
    });
  });
