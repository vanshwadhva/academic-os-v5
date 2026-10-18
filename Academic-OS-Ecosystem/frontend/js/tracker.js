// Academic OS tracker (extracted from index.html so the page satisfies the
// Chrome extension CSP, which forbids inline scripts).
  // ---------- DATA ----------
  const TODAY = new Date('2026-06-20');

  // Existing four-course curriculum, now assigned to Trimester 1.
  const TRIMESTER_1_COURSES = [
    {
      id: 'sm',
      name: 'Statistical Modelling and Inferencing',
      color: 'var(--sm-color)',
      bg: 'var(--sm-bg)',
      credits: '3 credits, 13 weeks',
      weeks: [
        { n: 1, date: '2026-05-23', topic: 'Basic Probability and Statistics', syllabus: ['Revision of basic probability', 'Random variables and distributions', 'Parametric vs non parametric', 'Population vs sample, central tendency'] },
        { n: 2, date: '2026-05-30', topic: 'Introduction to Statistical Inference', syllabus: ['The art of sampling', 'Point estimation', 'Properties of estimators', 'Central limit theorem', 'Simple random and stratified sampling'] },
        { n: 3, date: '2026-06-06', topic: 'Estimation and Hypothesis Testing', syllabus: ['Interval estimation of mean', 'Determining sample size', 'Hypothesis testing framework, errors and p values', 'One sample tests, Z and T', 'Quiz 1 covers weeks 1 to 3, weightage 15%'] },
        { n: 4, date: '2026-06-13', topic: 'Hypothesis Testing, continued', syllabus: ['Inferences for two population means', 'Inferences for two population variances', 'Testing population proportions', 'Chi square test of independence', 'A/B testing case study'] },
        { n: 5, date: '2026-06-20', topic: 'Analysis of Variance (ANOVA)', syllabus: ['Experimental design and ANOVA', 'One way ANOVA', 'Between group vs within group variance', 'F statistic calculation', 'Tukey HSD post hoc testing'] },
        { n: 6, date: '2026-06-27', topic: 'Simple Linear Regression', syllabus: ['Least squares method', 'Coefficient of determination, R squared', 'Significance testing, F and T', 'Residual analysis', 'Quiz 2 covers weeks 4 to 6, weightage 15%'] },
        { n: 7, date: '2026-07-04', topic: 'Multiple Regression', syllabus: ['The multiple regression model', 'Least squares in multiple regression', 'Adjusted R squared', 'Significance testing', 'Multicollinearity'] },
        { n: 8, date: '2026-07-11', topic: 'Forecasting and Time Series Analysis', syllabus: ['Time series components', 'Smoothing methods, moving averages', 'Exponential smoothing', 'Trend and seasonal components'] },
        { n: 9, date: '2026-07-18', topic: 'Factor and Cluster Analysis', syllabus: ['What is factor analysis', 'Conditions for factor analysis', 'PCA vs factor analysis', 'Interpreting the output'] },
        { n: 10, date: '2026-07-25', topic: 'Cluster Analysis', syllabus: ['Hierarchical clustering', 'K means clustering', 'Choosing the number of clusters K', 'Take home assignment covers weeks 1 to 10, weightage 20%'] },
        { n: 11, date: '2026-08-01', topic: 'Maximum Likelihood Methods', syllabus: ['Intuition of maximum likelihood', 'The likelihood function', 'Finding the MLE', 'Properties of MLEs', 'Quiz 3 covers weeks 7 to 11, weightage 15%'] },
        { n: 12, date: '2026-08-08', topic: 'Logistic Regression', syllabus: ['Linear probability model', 'Probit and logit models', 'Interpreting logit coefficients', 'Odds ratios'] },
        { n: 13, date: '2026-08-15', topic: 'Introduction to Bayesian Inference, Final Exam', syllabus: ['The Bayesian philosophy', 'End of trimester exam covers weeks 1 to 13, weightage 35%'] }
      ]
    },
    {
      id: 'dp',
      name: 'Data Preprocessing',
      color: 'var(--dp-color)',
      bg: 'var(--dp-bg)',
      credits: '2 credits, 8 weeks',
      weeks: [
        { n: 1, date: '2026-05-22', topic: 'Introduction to Data Science', syllabus: ['Foundations of data science', 'Knowledge Discovery in Databases process', 'Predictive vs descriptive data mining', 'Applications of data mining methods'] },
        { n: 2, date: '2026-05-29', topic: 'Data, attribute types and representation', syllabus: ['What is a dataset', 'Types of attributes', 'Data representation methods', 'Lab, setting up Colab, intro to pandas and matplotlib'] },
        { n: 3, date: '2026-06-05', topic: 'Data Quality and Issues', syllabus: ['Understanding data quality', 'Noise vs outliers', 'Missing values vs duplicate data', 'Data integrity challenges'] },
        { n: 4, date: '2026-06-12', topic: 'Data Cleaning', syllabus: ['Handling missing values', 'Dealing with noisy data', 'Outlier detection and management', 'Inconsistent data', 'Lab, fixing missing data and removing outliers'] },
        { n: 5, date: '2026-06-19', topic: 'Data Transformation and Aggregation', syllabus: ['Normalization techniques', 'Standardization', 'Data aggregation', 'Data integration for consistency', 'Lab, normalization and aggregation techniques'] },
        { n: 6, date: '2026-06-26', topic: 'Data Reduction', syllabus: ['Data sampling', 'Attribute subset selection', 'Feature creation', 'Lab, PCA for dimensionality reduction'] },
        { n: 7, date: '2026-07-03', topic: 'Proximity Measures', syllabus: ['Nominal, binary, numerical attributes', 'Ordinal and mixed attributes', 'Advanced similarity measures', 'Lab, proximity analysis on different attribute types'] },
        { n: 8, date: '2026-07-10', topic: 'Data Explainability, SHAP and LIME', syllabus: ['Data distribution analysis', 'Feature importance', 'Explainability in practice', 'Lab, SHAP and LIME walkthrough'] }
      ]
    },
    {
      id: 'fe',
      name: 'Feature Engineering',
      color: 'var(--fe-color)',
      bg: 'var(--fe-bg)',
      credits: '2 credits, 8 weeks',
      weeks: [
        { n: 1, date: '2026-06-20', topic: 'Overview of Feature Engineering', syllabus: ['Role and purpose of feature engineering', 'Feature importance, illustrative examples', 'Challenges of high dimensional data', 'General techniques overview'] },
        { n: 2, date: '2026-06-27', topic: 'Handling Numeric Data', syllabus: ['Discretization of continuous features', 'Min max, standardization, robust scaling', 'Smoothing methods', 'Log, polynomial and power transformations'] },
        { n: 3, date: '2026-07-04', topic: 'General Feature Engineering Techniques', syllabus: ['Feature extraction and construction', 'Filter based selection, correlation and chi square', 'Wrapper methods, SFS and SBS', 'Embedded feature selection'] },
        { n: 4, date: '2026-07-11', topic: 'Dimensionality Reduction (PCA, SVD, t-SNE)', syllabus: ['PCA concepts and applications', 'SVD for compression and noise reduction', 't-SNE for nonlinear reduction and visualization', 'Graded quiz at end of week'] },
        { n: 5, date: '2026-07-18', topic: 'Feature Engineering for Text Data', syllabus: ['Unigrams, n-grams, Bag of Words, TF-IDF', 'Word embeddings and one hot encoding', 'POS tagging and linguistic enrichment', 'Assignment opens this week'] },
        { n: 6, date: '2026-07-25', topic: 'Feature Engineering for Image Data', syllabus: ['Fundamentals of image representation', 'Edge detection techniques', 'Corner detection methods', 'Histogram of Oriented Gradients, HoG'] },
        { n: 7, date: '2026-08-01', topic: 'Feature Engineering for Time Series Data', syllabus: ['Lag features, rolling statistics, window features', 'Heart rate variability, moving averages, RSI, Bollinger Bands', 'Effect of engineered features on forecasting accuracy'] },
        { n: 8, date: '2026-08-08', topic: 'Automated Feature Engineering', syllabus: ['Deep Feature Synthesis with Featuretools', 'Automated time series extraction with TSFresh', 'Feature selection with Featurewiz', 'Integrating automated tools into ML workflows'] }
      ]
    },
    {
      id: 'dv',
      name: 'Data Visualization and Storytelling',
      color: 'var(--dv-color)',
      bg: 'var(--dv-bg)',
      credits: '3 credits, 13 weeks',
      weeks: [
        { n: 1, date: '2026-05-22', topic: 'Introduction to Visualization', syllabus: ['Need to visualize data', 'Seven stages of data visualization', 'Comparison, distribution, composition, relationship charts', 'Exploratory vs explanatory analysis'] },
        { n: 2, date: '2026-05-29', topic: 'Taxonomy of Data Visualization Methods', syllabus: ['Choosing an effective visual', 'Lessons in storytelling', 'Hierarchies and part to whole relationships', 'Showing change over time, plotting relationships, geo spatial data'] },
        { n: 3, date: '2026-06-05', topic: 'Effective Visuals Design', syllabus: ['Cognitive load and clutter', 'Gestalt principles of visual medium', 'Pre attentive attributes in text, tables and graphs', 'Strategic use of color'] },
        { n: 4, date: '2026-06-12', topic: 'Visual Best Practices, numerical and text data', syllabus: ['Edward Tufte visual encoding', 'Choosing the right chart for structured data', 'Word clouds, scatterplots, histograms for text', 'Topic models and word embeddings'] },
        { n: 5, date: '2026-06-19', topic: 'Dashboards', syllabus: ['Types and characteristics of dashboards', 'Common mistakes in dashboard design', 'Visual design process', 'Designing dashboards for usability'] },
        { n: 6, date: '2026-06-26', topic: 'Visual Storytelling', syllabus: ['Why storytelling matters', 'Author driven vs reader driven narratives', 'Seven story types', 'Misleading with charts'] },
        { n: 7, date: '2026-07-03', topic: 'Python Matplotlib', syllabus: ['Matplotlib basics and getting started', 'Plot styles and types', 'Advanced matplotlib'] },
        { n: 8, date: '2026-07-10', topic: 'Python Matplotlib, continued', syllabus: ['Plotting from a database and CSV', 'Plotting data from the web', 'Plotting geographical data', 'Curve fitting and extrapolation'] },
        { n: 9, date: '2026-07-17', topic: 'Python Seaborn', syllabus: ['Seaborn vs matplotlib', 'Statistical relationships', 'Categorical, univariate, bivariate distributions', 'Seaborn linear regression models'] },
        { n: 10, date: '2026-07-24', topic: 'Python Bokeh', syllabus: ['Bokeh building blocks and glyphs', 'Simple plots and different data structures', 'Decorating visuals', 'Interactive server side applications'] },
        { n: 11, date: '2026-07-31', topic: 'Tableau', syllabus: ['Tableau ecosystem and desktop basics', 'Data connections and metadata management', 'Data extracts, joins and blending'] },
        { n: 12, date: '2026-08-07', topic: 'Tableau, continued', syllabus: ['Visual analysis, sorting, grouping', 'Building an advanced dashboard', 'Tableau stories'] },
        { n: 13, date: '2026-08-14', topic: 'Power BI and Google Data Studio', syllabus: ['Google Data Studio, connect and visualize', 'Power BI data connections', 'Dashboard design and sharing'] }
      ]
    }
  ];

  const TRIMESTER_1_DEADLINES = [
    { date: '2026-06-09', title: 'Quiz 1 deadline', sub: 'Data Preprocessing, Statistical Modelling, Data Visualization' },
    { date: '2026-06-30', title: 'Quiz 2 deadline', sub: 'Data Preprocessing, Statistical Modelling, Data Visualization, and Feature Engineering Quiz 1' },
    { date: '2026-07-21', title: 'Quiz 3 deadline', sub: 'Statistical Modelling, Data Visualization, and Feature Engineering Quiz 2' },
    { date: '2026-08-08', title: 'Assignment deadline, all 4 courses', sub: 'Data Preprocessing, Statistical Modelling, Data Visualization, Feature Engineering' }
  ];

  const TRIMESTERS = [
    { id: 1, name: 'Trimester 1', description: 'DPP · FE · Statistics · DVS', courses: TRIMESTER_1_COURSES, deadlines: TRIMESTER_1_DEADLINES },
    { id: 2, name: 'Trimester 2', description: 'DSP handbook tracker', courses: DSP_BITS_COURSES, deadlines: DSP_BITS_DEADLINES },
    { id: 3, name: 'Trimester 3', description: 'Semester not yet started', courses: [], deadlines: [] },
    { id: 4, name: 'Trimester 4', description: 'Semester not yet started', courses: [], deadlines: [] },
    { id: 5, name: 'Trimester 5', description: 'Semester not yet started', courses: [], deadlines: [] },
    { id: 6, name: 'Trimester 6', description: 'Semester not yet started', courses: [], deadlines: [] }
  ];

  let currentTrimester = null;
  let COURSES = [];
  let DEADLINES = [];

  // ---------- FIREBASE OR MOCK INITIALIZATION ----------
  const LOCAL_OFFLINE_KEY = 'dsp_bits_tracker_progress_v1';
  const LEGACY_OFFLINE_KEY = 'msc_tracker_progress_v2';
  const PRIVATE_STORE_KEY = 'dsp_bits_tracker_cloud_sync_v1';

  // Remove credentials saved by the retired local-development token flow.
  localStorage.removeItem('lumen_access_token');
  localStorage.removeItem('lumen_user_id');
  localStorage.removeItem('firebaseToken');

  const BACKEND_API_URL = window.APP_CONFIG?.API_URL || "https://academic-os-api.onrender.com";

  let db   = null;
  let auth = null;
  let appId = 'dsp-bits-tracker';
  let isFirebaseConfigured = false;

  // Initialize Firebase directly — config is not a secret (security enforced by Firebase rules)
  try {
    const firebaseConfig = {
      apiKey:            "AIzaSyCTNPwLzpWNUI7ltQFJtv_E4W3oZQWnflQ",
      authDomain:        "bits-dsai-tracker.firebaseapp.com",
      projectId:         "bits-dsai-tracker",
      storageBucket:     "bits-dsai-tracker.firebasestorage.app",
      messagingSenderId: "530627005818",
      appId:             "1:530627005818:web:24ca6180f9ed9e2fcbdac3",
    };
    firebase.initializeApp(firebaseConfig);
    auth = firebase.auth();
    db   = firebase.firestore();
    isFirebaseConfigured = true;
    console.log("Firebase initialised — project: bits-dsai-tracker");
  } catch (err) {
    console.warn("Firebase init failed, falling back to offline simulation.", err);
  }

  // Simulated Database Fallback to allow complete functionality instantly inside plain environments
  const simulatedDB = {
    activeSession: JSON.parse(localStorage.getItem('simulated_session') || 'null'),
    progressStore: JSON.parse(localStorage.getItem('simulated_firestore_db') || '{}'),
    
    save() {
      localStorage.setItem('simulated_session', JSON.stringify(this.activeSession));
      localStorage.setItem('simulated_firestore_db', JSON.stringify(this.progressStore));
    }
  };

  // ---------- TRACKER STATE ----------
  let progress = {};
  let liveLumenPayload = null;
  let lastLumenFetchAt = 0;
  let lumenSyncInFlight = false;
  let lastTrackerSnapshotUploadSucceeded = true;
  let extensionBridgeReady = false;
  let activeFilter = 'all';
  let openSections = {};
  let currentUser = null;
  let isAuthLoading = true;
  let legacyProgressMigrationPending = false;

  // ---------- INITIALIZE APP & AUTH LISTENERS ----------
  window.onload = async function() {
    setupAuthDOMListeners();
    if (window.AcademicOSBridge?.initialize) {
    window.AcademicOSBridge.initialize();
}
    
    if (isFirebaseConfigured) {
      // Rule 3: Auth first. Listen to changes
      auth.onAuthStateChanged(async (user) => {
        isAuthLoading = false;
        document.getElementById('appInitLoader').classList.add('hidden');
        
        if (user) {
          const email = user.email || "";
          if (isAuthorizedGoogleUser(user)) {
            currentUser = user;
            await initializeUserDashboard(user);
          } else {
            currentUser = null;
            const message = isValidBitsEmail(email)
              ? "Please sign in with your official BITS Google account."
              : "Only @bitspilani-digital.edu.in Google accounts are permitted.";
            showAuthAlert(message, "error");
            await auth.signOut();
            showAuthPortal();
          }
        } else {
          currentUser = null;
          showAuthPortal();
        }
      });
    } else {
      // Simulation Authentication State Loop
      setTimeout(async () => {
        isAuthLoading = false;
        document.getElementById('appInitLoader').classList.add('hidden');
        
        // Simulated sessions are no longer created or restored; discard any leftover one.
        simulatedDB.activeSession = null;
        simulatedDB.save();
        showAuthPortal();
      }, 700);
    }
  };

  // ---------- DOMAIN VERIFICATION GATES ----------
  // Chrome extension pages cannot use popup sign-in. In an extension the Google
  // OAuth implicit flow runs inside chrome.identity and the returned ID token is
  // exchanged with Firebase.
  function isChromeExtensionContext() {
    return window.location.protocol === 'chrome-extension:' && typeof chrome !== 'undefined' && !!chrome.identity;
  }

  function randomNonce() {
    const bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);
    return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
  }

  function jwtPayload(token) {
    const base64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    return JSON.parse(decodeURIComponent(atob(base64).split('').map(c => '%' + c.charCodeAt(0).toString(16).padStart(2, '0')).join('')));
  }

  async function signInWithChromeIdentity() {
    const clientId = window.APP_CONFIG?.GOOGLE_OAUTH_CLIENT_ID;
    if (!clientId) {
      throw new Error('GOOGLE_OAUTH_CLIENT_ID is not set in this build of the extension.');
    }
    const nonce = randomNonce();
    const params = new URLSearchParams({
      client_id: clientId,
      response_type: 'id_token',
      redirect_uri: chrome.identity.getRedirectURL(),
      scope: 'openid email profile',
      nonce,
      prompt: 'select_account',
      hd: 'bitspilani-digital.edu.in'
    });
    const responseUrl = await new Promise((resolve, reject) => {
      chrome.identity.launchWebAuthFlow(
        { url: `https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`, interactive: true },
        (url) => {
          if (chrome.runtime.lastError || !url) {
            reject(new Error(chrome.runtime.lastError?.message || 'Sign-in was cancelled.'));
          } else {
            resolve(url);
          }
        }
      );
    });
    const idToken = new URLSearchParams(new URL(responseUrl).hash.replace(/^#/, '')).get('id_token');
    if (!idToken) throw new Error('Google did not return an ID token.');
    if (jwtPayload(idToken).nonce !== nonce) throw new Error('Google sign-in response did not match this request.');
    await auth.signInWithCredential(firebase.auth.GoogleAuthProvider.credential(idToken));
  }

  function isValidBitsEmail(email) {
    const rx = /^[a-zA-Z0-9._%+-]+@bitspilani-digital\.edu\.in$/i;
    return rx.test(email);
  }

  function isAuthorizedGoogleUser(user) {
    return isValidBitsEmail(user?.email || '') &&
      (user?.providerData || []).some(profile => profile.providerId === 'google.com');
  }

  // ---------- GOOGLE SIGN-IN CONTROLLER ----------
  function setupAuthDOMListeners() {
    const googleAuthBtn = document.getElementById('googleAuthBtn');

    const refreshLumenWhenVisible = async () => {
      if (document.visibilityState !== 'visible' || !currentUser || !COURSES.length || !liveLumenPayload) return;
      if (Date.now() - lastLumenFetchAt < 5 * 60 * 1000) return;
      if (await syncProgressFromLumen({ interactive: false })) render();
    };
    document.addEventListener('visibilitychange', refreshLumenWhenVisible);
    window.addEventListener('focus', refreshLumenWhenVisible);

    // Google Sign-In click listener. Firebase is the only sign-in path: there is
    // no simulated account picker (that would let anyone open a session locally).
    googleAuthBtn.addEventListener('click', async () => {
      hideAuthAlert();
      setAuthLoadingState(true);

      if (!isFirebaseConfigured) {
        showAuthAlert("Sign-in is unavailable because Firebase could not start. Reload the page and try again.", "error");
        setAuthLoadingState(false);
        return;
      }

      try {
        if (isChromeExtensionContext()) {
          await signInWithChromeIdentity();
        } else {
          const provider = new firebase.auth.GoogleAuthProvider();
          // Hint only; the server and onAuthStateChanged enforce the domain.
          provider.setCustomParameters({ hd: 'bitspilani-digital.edu.in' });
          const result = await auth.signInWithPopup(provider);
          if (!isAuthorizedGoogleUser(result.user)) {
            showAuthAlert("Access denied. Sign in with an official @bitspilani-digital.edu.in Google account.", "error");
            await auth.signOut();
          }
        }
      } catch (error) {
        console.error("Google Auth failed: ", error);
        showAuthAlert("Google Authentication failed: " + error.message, "error");
        setAuthLoadingState(false);
      }
    });

    document.querySelectorAll('.trimester-choice').forEach(button => {
      button.addEventListener('click', () => selectTrimester(Number(button.dataset.trimester)));
    });

    document.getElementById('changeTrimesterBtn').addEventListener('click', showTrimesterChooser);
    document.getElementById('chooserSignOutBtn').addEventListener('click', signOutCurrentUser);

    // Reset Progress Metrics Trigger
    document.getElementById('resetBtn').addEventListener('click', async () => {
      const confirmReset = await showCustomConfirm("Are you sure you want to reset all tracking progress on this account? This will clear your modules checklist on the Cloud.");
      if (confirmReset) {
        progress = {};
        localStorage.removeItem(LOCAL_OFFLINE_KEY);
        localStorage.removeItem(LEGACY_OFFLINE_KEY);
        await syncProgressToCloud();
        render();
      }
    });

    document.getElementById('lumenSyncBtn').addEventListener('click', async () => {
      if (window.AcademicOSBridge?.requestFreshProgress) {
    window.AcademicOSBridge.requestFreshProgress();
}
      await syncProgressFromLumen({ interactive: true });
      render();
    });

    // Sign out trigger
    document.getElementById('signOutBtn').addEventListener('click', signOutCurrentUser);
  }

  async function signOutCurrentUser() {
    setAuthLoadingState(false);
    hideAuthAlert();

    if (isFirebaseConfigured) {
      await auth.signOut();
    } else {
      simulatedDB.activeSession = null;
      simulatedDB.save();
      currentUser = null;
      showAuthPortal();
    }
  }

  function setAuthLoadingState(loading) {
    const btn = document.getElementById('googleAuthBtn');
    btn.disabled = loading;
    btn.style.opacity = loading ? '0.7' : '1';
    btn.querySelector('span').innerText = loading ? 'Signing in...' : 'Continue with Google';
  }

  function showAuthAlert(msg, type) {
    const alertBox = document.getElementById('authAlert');
    alertBox.className = `auth-alert ${type}`;
    alertBox.innerText = msg;
  }

  function hideAuthAlert() {
    const alertBox = document.getElementById('authAlert');
    alertBox.style.display = 'none';
  }

  function showAuthPortal() {
    document.getElementById('mainTrackerApp').classList.add('hidden');
    document.getElementById('trimesterChooser').classList.add('hidden');
    const portal = document.getElementById('authPortal');
    portal.style.display = 'block';
    setAuthLoadingState(false);
  }

  function showTrimesterChooser() {
    document.getElementById('authPortal').style.display = 'none';
    document.getElementById('mainTrackerApp').classList.add('hidden');
    document.getElementById('trimesterChooser').classList.remove('hidden');
  }

  async function selectTrimester(trimesterId) {
    const trimester = TRIMESTERS.find(item => item.id === trimesterId);
    if (!trimester) return;

    currentTrimester = trimester;
    COURSES = trimester.courses;
    DEADLINES = trimester.deadlines;
    activeFilter = 'all';
    openSections = {};
    COURSES.forEach(course => openSections[course.id] = true);

    const label = document.getElementById('activeTrimesterLabel');
    label.textContent = trimester.id === 1
      ? 'Trimester 1 · Existing study tracker'
      : trimester.id === 2
        ? 'Trimester 2 · Data Stores & Pipeline'
        : trimester.name;

    document.getElementById('trimesterChooser').classList.add('hidden');
    document.getElementById('mainTrackerApp').classList.remove('hidden');

    if (!COURSES.length) {
      setSyncState(trimester.description, false);
      render();
      return;
    }

    setSyncState('Loading trimester progress...', true);
    if (window.AcademicOSBridge?.requestCachedProgress) {
      window.AcademicOSBridge.requestCachedProgress();
    }
    const lumenSynced = await syncProgressFromLumen({ interactive: false });
    if (!lumenSynced) await syncProgressToCloud();
    render();
  }

  // ---------- USER DASHBOARD LOADER & DATA MIGRATION ----------
  async function initializeUserDashboard(user) {
    liveLumenPayload = null;
    predictionInsights = null;
    studentProfile = {};
    studentProfileLoaded = false;
    lastLumenFetchAt = 0;
    document.getElementById('authPortal').style.display = 'none';
    document.getElementById('mainTrackerApp').classList.add('hidden');
    document.getElementById('trimesterChooser').classList.remove('hidden');
    const trimesterChoices = Array.from(document.querySelectorAll('.trimester-choice'));
    const pickerHelp = document.querySelector('.trimester-picker-help');
    trimesterChoices.forEach(button => button.disabled = true);
    pickerHelp.textContent = 'Loading your saved progress...';
    
    const displayName = user.displayName || (user.email ? user.email.split('@')[0] : 'Authorized Student');
    document.getElementById('userBadgeEmail').innerText = displayName;
    document.getElementById('userBadgeEmail').title = user.email || displayName;
    document.getElementById('chooserUserBadge').innerText = displayName;
    document.getElementById('chooserUserBadge').title = user.email || displayName;

    setSyncState("Fetching Cloud metrics...", true);
    progress = await fetchUserProgressFromCloud(user.uid);
    const migratedKeys = [];
    for (const storageKey of [LEGACY_OFFLINE_KEY, LOCAL_OFFLINE_KEY]) {
      const offlineProgressRaw = localStorage.getItem(storageKey);
      if (!offlineProgressRaw) continue;
      try {
        const offlineProgress = JSON.parse(offlineProgressRaw);
        const mergedProgress = mergeProgress(progress, offlineProgress);
        if (JSON.stringify(mergedProgress) !== JSON.stringify(progress)) {
          progress = mergedProgress;
          migratedKeys.push(storageKey);
        }
      } catch (e) {
        console.warn(`Offline migration parse warning for ${storageKey}:`, e);
      }
    }

    let progressSyncFailed = false;
    if (legacyProgressMigrationPending || migratedKeys.length) {
      const progressSaved = await syncProgressToCloud();
      if (progressSaved) migratedKeys.forEach(storageKey => localStorage.removeItem(storageKey));
      else progressSyncFailed = true;
    }

    if (!progressSyncFailed) setSyncState("Cloud synced", false);
    pickerHelp.textContent = 'Choose one of the six trimester trackers.';
    trimesterChoices.forEach(button => button.disabled = false);
  }

  // ---------- LUMEN LMS DATALAYER ----------
  async function getFirebaseAuthHeaders() {
    if (!isFirebaseConfigured || !auth.currentUser) return {};
    const token = await auth.currentUser.getIdToken();
    return { Authorization: `Bearer ${token}` };
  }

  async function syncProgressFromLumen({ interactive = false } = {}) {
    if (!currentUser || lumenSyncInFlight) return false;

    lumenSyncInFlight = true;
    lastLumenFetchAt = Date.now();
    setSyncState("Fetching Lumen progress...", true);
    const params = new URLSearchParams({ student_id: currentUser.uid });

    try {
      const response = await fetch(`${BACKEND_API_URL}/api/lumen/progress?${params.toString()}`, {
        headers: await getFirebaseAuthHeaders()
      });
      const payload = await response.json();

      if (!response.ok) {
        const detail = payload.detail || {};
        if (response.status === 403 && detail.connect_url) {
          setSyncState("Lumen connection required", false);
          if (interactive) window.location.href = detail.connect_url;
          return false;
        }
        throw new Error(detail.message || detail || "Lumen sync failed");
      }

      liveLumenPayload = normalizeLumenPayload(payload);
      predictionInsights = payload.insights || null;
      const progressSaved = await syncProgressToCloud();
      if (progressSaved && lastTrackerSnapshotUploadSucceeded) {
        setSyncState("Live Lumen progress synced", false);
      }
      if (currentTrimester && COURSES.length) render();
      return true;
    } catch (err) {
      console.warn("Lumen sync unavailable; using saved tracker progress.", err);
      setSyncState(interactive ? "Lumen sync failed" : "Using saved tracker metrics", false);
      return false;
    } finally {
      lumenSyncInFlight = false;
    }
  }

  function normalizeLumenPayload(payload) {
    const courses = Array.isArray(payload.courses) ? payload.courses : [];
    return {
      last_synced_at: payload.last_synced_at || new Date().toISOString(),
      courses: courses.map(course => ({
        course_id: String(course.course_id || ''),
        course_name: course.course_name || 'Lumen course',
        course_code: course.course_code || '',
        modules_progress_available: course.module_progress_available === true || (
          course.module_progress_available !== false &&
          (course.modules || []).some(module => ['visited', 'is_read', 'completed'].some(key => module[key] !== undefined && module[key] !== null))
        ),
        modules_completed: Number(course.modules_completed || 0),
        modules_total: Number(course.modules_total || (course.modules || []).length),
        modules: (course.modules || []).map(module => ({
          topic_id: String(module.topic_id || module.id || ''),
          title: module.title || 'Untitled lecture',
          visited: module.visited === undefined || module.visited === null ? null : !!module.visited,
          is_read: module.is_read === undefined || module.is_read === null ? null : !!module.is_read,
          completed: module.completed === undefined || module.completed === null ? null : !!module.completed,
          last_visited: module.last_visited || null,
          num_visits: Number(module.num_visits || 0),
          total_time_seconds: Number(module.total_time_seconds || 0)
        })),
        quizzes: (course.quizzes || []).map(quiz => ({
          quiz_id: String(quiz.lms_quiz_id || quiz.quiz_id || ''),
          title: quiz.quiz_name || quiz.name || 'Untitled quiz',
          status: String(quiz.status || 'pending').toLowerCase(),
          score_pct: quiz.percentage === null || quiz.percentage === undefined || quiz.percentage === ''
            ? null
            : Number.isFinite(Number(quiz.percentage)) ? Number(quiz.percentage) : null,
          updated_at: quiz.submitted_at || null
        })),
        assignments: (course.assignments || []).map(assignment => ({
          assignment_id: String(assignment.assignment_id || ''),
          title: assignment.name || 'Untitled assignment',
          status: assignment.submission_status || (assignment.is_submitted ? 'submitted' : 'pending'),
          completed: !!assignment.is_submitted,
          updated_at: assignment.submitted_at || null
        }))
      }))
    };
  }

  function matchLocalCourse(lmsCourse, localCourses = COURSES) {
    const normalize = value => String(value || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
    const nameText = normalize(lmsCourse.course_name);
    const codeText = normalize(lmsCourse.course_code);
    const nameTokens = new Set(nameText.split(/\s+/).filter(Boolean));
    const codeTokens = new Set(codeText.split(/\s+/).filter(Boolean));
    const aliases = {
      sm: ['statistics', 'statistical modelling', 'statistical modeling', 'statistical modelling and inferencing', 'smi', 'sm'],
      dp: ['data preprocessing', 'data pre processing', 'dpp', 'dp'],
      fe: ['feature engineering', 'fe'],
      dv: ['data visualization and storytelling', 'data visualisation and storytelling', 'dvs', 'dv'],
      dsp: ['data stores and pipeline', 'data stores pipeline', 'dsp']
    };

    const exactMatch = localCourses.find(course => {
      const courseName = normalize(course.name);
      if (nameText.includes(courseName)) return true;
      return (aliases[course.id] || []).some(alias => {
        const normalizedAlias = normalize(alias);
        if (normalizedAlias.includes(' ')) {
          return nameText.includes(normalizedAlias) || codeText.includes(normalizedAlias);
        }
        return nameTokens.has(normalizedAlias) || codeTokens.has(normalizedAlias);
      });
    });
    if (exactMatch) return exactMatch;

    const ignoredWords = new Set(['data', 'and', 'the', 'of', 'in', 'to']);
    let bestMatch = null;
    let bestScore = 0;
    localCourses.forEach(course => {
      const specificWords = normalize(course.name).split(/\s+/)
        .filter(word => word.length > 3 && !ignoredWords.has(word));
      const score = specificWords.filter(word => nameTokens.has(word) || codeTokens.has(word)).length;
      if (score > bestScore) {
        bestMatch = course;
        bestScore = score;
      }
    });
    return bestScore > 0 ? bestMatch : undefined;
  }

  function mergeProgress(savedProgress, lmsProgress) {
    const merged = JSON.parse(JSON.stringify(savedProgress || {}));
    Object.keys(lmsProgress || {}).forEach(courseId => {
      if (!merged[courseId]) merged[courseId] = {};
      Object.keys(lmsProgress[courseId]).forEach(weekN => {
        if (!merged[courseId][weekN]) merged[courseId][weekN] = {};
        Object.keys(lmsProgress[courseId][weekN]).forEach(modIdx => {
          if (lmsProgress[courseId][weekN][modIdx]) {
            merged[courseId][weekN][modIdx] = true;
          }
        });
      });
    });
    return merged;
  }

  function getLumenCourseForTrackerCourse(course) {
    const lumenCourses = liveLumenPayload?.courses || [];
    return lumenCourses.find(lumenCourse => matchLocalCourse(lumenCourse, [course])?.id === course.id);
  }

  function buildLumenCourseProgressSnapshot(course) {
    const lumenCourse = getLumenCourseForTrackerCourse(course);
    if (!lumenCourse) return null;

    const lectures = lumenCourse.modules || [];
    const quizzes = lumenCourse.quizzes || [];
    const assignments = lumenCourse.assignments || [];
    const lectureStatusAvailable = lumenCourse.modules_progress_available !== false;
    const isViewed = item => !!(item.visited || item.is_read || item.completed);
    const isQuizComplete = quiz => String(quiz.status || '').toLowerCase() === 'completed';
    const isAssignmentSubmitted = assignment => !!assignment.completed || String(assignment.status || '').toLowerCase() === 'submitted';

    const activities = [
      ...lectures.map(lecture => ({
        kind: 'lecture',
        item_id: lecture.topic_id || null,
        title: lecture.title,
        status: lecture.completed ? 'Completed' : (lecture.visited || lecture.is_read) ? 'Viewed' : lectureStatusAvailable ? 'Not viewed' : 'Status unavailable',
        completed: isViewed(lecture),
        score_pct: null,
        updated_at: lecture.last_visited || null
      })),
      ...quizzes.map(quiz => ({
        kind: 'quiz',
        item_id: quiz.quiz_id || null,
        title: quiz.title,
        status: quiz.status || 'pending',
        completed: isQuizComplete(quiz),
        score_pct: quiz.score_pct,
        updated_at: quiz.updated_at || null
      })),
      ...assignments.map(assignment => ({
        kind: 'assignment',
        item_id: assignment.assignment_id || null,
        title: assignment.title,
        status: assignment.status || 'pending',
        completed: isAssignmentSubmitted(assignment),
        score_pct: null,
        updated_at: assignment.updated_at || null
      }))
    ];

    const lecturesTotal = Number(lumenCourse.modules_total || lectures.length);
    const lecturesViewed = lectureStatusAvailable
      ? lectures.filter(isViewed).length
      : Math.min(Number(lumenCourse.modules_completed || 0), lecturesTotal);
    const quizzesCompleted = quizzes.filter(isQuizComplete).length;
    const assignmentsSubmitted = assignments.filter(isAssignmentSubmitted).length;
    const completedActivities = lecturesViewed + quizzesCompleted + assignmentsSubmitted;
    const completionPct = activities.length
      ? Math.round((completedActivities / activities.length) * 1000) / 10
      : 0;

    return {
      completion_pct: completionPct,
      lecture_status_available: lectureStatusAvailable,
      lectures_viewed: lecturesViewed,
      lectures_total: lecturesTotal,
      quizzes_completed: quizzesCompleted,
      quizzes_total: quizzes.length,
      assignments_submitted: assignmentsSubmitted,
      assignments_total: assignments.length,
      activities,
      last_synced_at: liveLumenPayload?.last_synced_at || null
    };
  }

  function escapeMarkup(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  // ---------- CLOUD FIRESTORE DATALAYER ----------
  async function fetchUserProgressFromCloud(userId) {
    legacyProgressMigrationPending = false;
    if (isFirebaseConfigured) {
      try {
        if (!auth.currentUser) return {};
        const docRef = db.doc(`artifacts/${appId}/users/${userId}/progress/trackerData`);
        const snapshot = await docRef.get();
        const payload = snapshot.exists ? snapshot.data() : {};
        let savedProgress = payload.progress || {};
        liveLumenPayload = payload.lumenProgress || null;

        if (payload.legacyProgressImported !== true) {
          legacyProgressMigrationPending = true;
          try {
            const legacyDocRef = db.doc(`artifacts/msc-dsai-tracker/users/${userId}/progress/trackerData`);
            const legacySnapshot = await legacyDocRef.get();
            if (legacySnapshot.exists) {
              const legacyPayload = legacySnapshot.data();
              savedProgress = mergeProgress(savedProgress, legacyPayload.progress || {});
            }
          } catch (legacyErr) {
            console.warn("Legacy tracker progress could not be imported.", legacyErr);
          }
        }
        return savedProgress;
      } catch (err) {
        console.error("Firestore loading failure. Working with offline safety cache.", err);
      }
    } else {
      return simulatedDB.progressStore[userId] || {};
    }
    return {};
  }

  function buildTrackerSnapshot(trimester) {
    const courses = trimester.courses.map(course => ({
      course_id: course.id,
      course_name: course.name,
      lumen_progress: buildLumenCourseProgressSnapshot(course),
      weeks: course.weeks.map(week => {
        const moduleTitles = (week.syllabus && week.syllabus.length)
          ? week.syllabus
          : [week.topic || `Week ${week.n}`];
        return {
          week_label: String(week.label || week.n),
          topic: week.topic || null,
          case_study: week.caseStudy || null,
          modules: moduleTitles.map((title, index) => ({
            title,
            completed: getModuleState(course.id, week.n, index)
          }))
        };
      })
    }));

    return {
      trimester_id: trimester.id,
      trimester_name: trimester.name,
      courses,
      lumen_synced_at: liveLumenPayload?.last_synced_at || null
    };
  }

  async function uploadTrackerSnapshotToBackend() {
    lastTrackerSnapshotUploadSucceeded = true;
    if (!currentTrimester || !COURSES.length || !isFirebaseConfigured || !auth.currentUser) {
      return true;
    }

    try {
      const snapshots = TRIMESTERS
        .filter(trimester => trimester.courses.length)
        .map(buildTrackerSnapshot);
      const response = await fetch(`${BACKEND_API_URL}/api/tracker/progress`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...(await getFirebaseAuthHeaders())
        },
        body: JSON.stringify({ snapshots })
      });
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || `HTTP ${response.status}`);
      }
      return true;
    } catch (err) {
      lastTrackerSnapshotUploadSucceeded = false;
      console.warn('Admin cohort progress sync unavailable; personal tracker progress remains saved.', err);
      return false;
    }
  }

  async function syncProgressToCloud() {
    if (!currentUser) return false;

    setSyncState("Syncing data to Cloud...", true);
    let progressSaved = false;

    if (isFirebaseConfigured) {
      if (!auth.currentUser) return false;
      try {
        const docRef = db.doc(`artifacts/${appId}/users/${currentUser.uid}/progress/trackerData`);
        await docRef.set({
          progress: progress,
          lumenProgress: liveLumenPayload,
          legacyProgressImported: true,
          updatedAt: firebase.firestore.FieldValue.serverTimestamp()
        }, { merge: true });
        legacyProgressMigrationPending = false;
        progressSaved = true;
        setSyncState("Metrics saved securely in Cloud", false);
      } catch (err) {
        console.error("Firestore sync metrics error: ", err);
        setSyncState("Sync offline - auto retrying", false);
      }

      if (currentTrimester) {
        const cohortSnapshotSaved = await uploadTrackerSnapshotToBackend();
        if (!cohortSnapshotSaved && progressSaved) {
          setSyncState("Cloud saved; admin cohort sync unavailable", false);
        }
      }
      return progressSaved;
    }

    simulatedDB.progressStore[currentUser.uid] = progress;
    simulatedDB.save();
    legacyProgressMigrationPending = false;
    setSyncState("Metrics saved offline", false);
    return true;
  }

  function setSyncState(message, active) {
    const el = document.getElementById('syncStatus');
    el.innerText = message;
    if (active) {
      el.classList.add('syncing-pulse');
    } else {
      el.classList.remove('syncing-pulse');
    }
  }

  // ---------- DYNAMIC MODAL REPLACEMENTS ----------
  function showCustomConfirm(msg) {
    return new Promise((resolve) => {
      const confirmUI = document.createElement('div');
      confirmUI.setAttribute('style', `
        position: fixed;
        top: 0; left: 0; right: 0; bottom: 0;
        background: rgba(15, 23, 42, 0.4);
        backdrop-filter: blur(2px);
        display: flex; align-items: center; justify-content: center;
        z-index: 9999;
        font-family: 'Inter', sans-serif;
      `);
      confirmUI.innerHTML = `
        <div style="background: white; width: 100%; max-width: 400px; padding: 24px; border-radius: 16px; box-shadow: 0 10px 25px rgba(0,0,0,0.1); border: 1px solid var(--border);">
          <div style="font-weight: 700; font-size: 16px; color: var(--text); margin-bottom: 12px;">BITS Tracker Portal</div>
          <div style="font-size: 13.5px; color: var(--text-soft); line-height: 1.5; margin-bottom: 24px;">${msg}</div>
          <div style="display: flex; justify-content: flex-end; gap: 10px;">
            <button id="cancelConf" style="background: #f1f2f4; border: none; padding: 9px 16px; font-weight: 600; border-radius: 8px; font-size: 13px; color: var(--text-soft); cursor: pointer;">Cancel</button>
            <button id="okConf" style="background: var(--text); border: none; padding: 9px 16px; font-weight: 600; border-radius: 8px; font-size: 13px; color: white; cursor: pointer;">Confirm</button>
          </div>
        </div>
      `;
      document.body.appendChild(confirmUI);
      
      confirmUI.querySelector('#cancelConf').addEventListener('click', () => {
        document.body.removeChild(confirmUI);
        resolve(false);
      });
      confirmUI.querySelector('#okConf').addEventListener('click', () => {
        document.body.removeChild(confirmUI);
        resolve(true);
      });
    });
  }

  // ---------- STATE CHANGERS ----------
  function getModuleState(courseId, weekN, modIdx) {
    return !!(progress[courseId] && progress[courseId][weekN] && progress[courseId][weekN][modIdx]);
  }

  function getWeekModulesCount(course, week) {
    return (week.syllabus && week.syllabus.length) ? week.syllabus.length : 1;
  }

  function getWeekDoneCount(course, week) {
    const total = getWeekModulesCount(course, week);
    let done = 0;
    for (let i = 0; i < total; i++) {
      if (getModuleState(course.id, week.n, i)) done++;
    }
    return done;
  }

  function isWeekStudied(course, week) {
    const total = getWeekModulesCount(course, week);
    return getWeekDoneCount(course, week) === total && total > 0;
  }

  async function toggleModule(courseId, weekN, modIdx) {
    if (!progress[courseId]) progress[courseId] = {};
    if (!progress[courseId][weekN]) progress[courseId][weekN] = {};
    progress[courseId][weekN][modIdx] = !progress[courseId][weekN][modIdx];
    await syncProgressToCloud();
    render();
  }

  async function toggleWholeWeek(course, week) {
    const courseId = course.id;
    const weekN = week.n;
    const total = getWeekModulesCount(course, week);
    const allDone = isWeekStudied(course, week);
    if (!progress[courseId]) progress[courseId] = {};
    if (!progress[courseId][weekN]) progress[courseId][weekN] = {};
    const target = !allDone;
    for (let i = 0; i < total; i++) {
      progress[courseId][weekN][i] = target;
    }
    await syncProgressToCloud();
    render();
  }

  async function toggleStudied(courseId, weekN) {
    const course = COURSES.find(c => c.id === courseId);
    const week = course.weeks.find(w => w.n === weekN);
    await toggleWholeWeek(course, week);
  }

  // ---------- HELPERS ----------
  function fmtDate(iso) {
    if (!iso) return 'Schedule from Lumen';
    const d = new Date(iso);
    return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
  }

  function weekStatus(course, week) {
    const studied = isWeekStudied(course, week);
    if (studied) return 'studied';
    if (!week.date) return 'pending';
    const wd = new Date(week.date);
    if (wd > TODAY) return 'upcoming';
    const doneCount = getWeekDoneCount(course, week);
    if (doneCount > 0) return 'partial';
    return 'pending';
  }

  function courseCompletion(course) {
    let total = 0, done = 0;
    course.weeks.forEach(w => {
      total += getWeekModulesCount(course, w);
      done += getWeekDoneCount(course, w);
    });
    return { done, total, pct: total ? Math.round((done / total) * 100) : 0 };
  }

  function overallCompletion() {
    let done = 0, total = 0;
    COURSES.forEach(c => {
      const r = courseCompletion(c);
      done += r.done;
      total += r.total;
    });
    return { done, total, pct: total ? Math.round((done / total) * 100) : 0 };
  }

  function deadlineState(iso) {
    if (!iso) return 'future';
    const d = new Date(iso);
    const diffDays = Math.round((d - TODAY) / (1000 * 60 * 60 * 24));
    if (diffDays < 0) return 'past';
    if (diffDays <= 7) return 'soon';
    return 'future';
  }

  const checkSvg = '<svg viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>';
  const chevronSvg = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>';

  // ---------- RENDER SCHEDULER ----------
  function render() {
    const hasCourses = COURSES.length > 0;
    ['summaryGrid', 'analyticsSection', 'predictionSection', 'timelinePostBar', 'filterRow', 'deadlineSection']
      .forEach(id => document.getElementById(id).classList.toggle('hidden', !hasCourses));

    if (!hasCourses) {
      document.getElementById('courseContainer').innerHTML =
        `<div class="trimester-empty-state">Semester not yet started</div>`;
      renderAnalytics();
      return;
    }

    renderSummary();
    renderPrediction();
    renderFilters();
    renderCourses();
    renderDeadlines();
    renderAnalytics();
  }

  function renderSummary() {
    const grid = document.getElementById('summaryGrid');
    const overall = overallCompletion();
    let html = `
      <div class="summary-card overall">
        <div class="label">Overall progress</div>
        <div class="value">${overall.pct}%</div>
        <div class="mini-bar"><div class="mini-bar-fill" style="width:${overall.pct}%; background:#5b6168;"></div></div>
      </div>
    `;
    COURSES.forEach(c => {
      const r = courseCompletion(c);
      html += `
        <div class="summary-card">
          <div class="label">${c.id.toUpperCase()}</div>
          <div class="value" style="color:${c.color}">${r.pct}%</div>
          <div class="mini-bar"><div class="mini-bar-fill" style="width:${r.pct}%; background:${c.color};"></div></div>
        </div>
      `;
    });
    grid.innerHTML = html;
  }

  // ---------- PLACEMENT PREDICTION (server model) ----------
  // The browser never computes a prediction. It shows what /api/students/me/insights
  // (or /api/lumen/progress) returns, including which inputs came from Lumen,
  // from the student, or from training-set defaults.
  let predictionInsights = null;
  let studentProfile = {};
  let studentProfileLoaded = false;
  let predictionListenersBound = false;

  const PROFILE_FIELDS = [
    { key: 'aptitude_score', label: 'Aptitude score (0–100)', min: 0, max: 100, integer: false },
    { key: 'communication_score', label: 'Communication score (0–100)', min: 0, max: 100, integer: false },
    { key: 'trimester_gpa', label: 'Trimester GPA (0–10)', min: 0, max: 10, integer: false },
    { key: 'backlogs_count', label: 'Backlogs', min: 0, max: 100, integer: true },
    { key: 'projects_count', label: 'Projects completed', min: 0, max: 100, integer: true },
    { key: 'internships_count', label: 'Internships', min: 0, max: 100, integer: true },
    { key: 'mock_interviews_attended', label: 'Mock interviews attended', min: 0, max: 1000, integer: true }
  ];

  const INSIGHT_LABELS = {
    preferred_study_hour: 'Preferred study hour',
    weekly_study_hours: 'Weekly study hours',
    consistency_score: 'Consistency',
    attendance_pct: 'Attendance %',
    backlogs_count: 'Backlogs',
    aptitude_score: 'Aptitude score',
    avg_quiz_score: 'Average quiz score',
    quiz_score_std: 'Quiz score spread',
    assignment_avg: 'Graded-item average',
    trimester_gpa: 'Trimester GPA',
    modules_completed_pct: 'Lectures completed %',
    communication_score: 'Communication score',
    projects_count: 'Projects completed',
    internships_count: 'Internships',
    mock_interviews_attended: 'Mock interviews attended'
  };

  const SOURCE_NAMES = { lumen: 'Lumen', self_reported: 'You', imputed: 'Default (no data)' };

  function renderPrediction() {
    const grid = document.getElementById('predictionGrid');
    if (!grid) return;
    bindPredictionListeners(grid);
    grid.innerHTML = `${renderPredictionSummary(predictionInsights)}${renderProfileForm()}`;
    if (!studentProfileLoaded) loadStudentProfile();
  }

  function bindPredictionListeners(grid) {
    if (predictionListenersBound) return;
    predictionListenersBound = true;
    grid.addEventListener('click', (event) => {
      if (event.target.closest('#predictionConnectBtn')) {
        syncProgressFromLumen({ interactive: true });
      }
    });
    grid.addEventListener('submit', onProfileSubmit);
  }

  function renderPredictionSummary(insights) {
    if (!insights) {
      return `
        <div class="prediction-card" style="grid-column: 1 / -1;">
          <div class="label">Placement estimate</div>
          <div class="value" style="font-size:15px;">Not available yet</div>
          <div style="color:var(--text-soft);font-size:12px;margin:6px 0 10px;">The estimate is based on your Lumen course activity. Connect Lumen to generate it.</div>
          <button type="button" id="predictionConnectBtn" class="reset-btn">Connect Lumen</button>
        </div>`;
    }

    if (insights.status !== 'ready') {
      return `
        <div class="prediction-card" style="grid-column: 1 / -1;">
          <div class="label">Placement estimate</div>
          <div class="value" style="font-size:15px;">${escapeMarkup(insights.message || 'Not available')}</div>
          ${insights.status === 'awaiting_lumen' ? '<button type="button" id="predictionConnectBtn" class="reset-btn">Connect Lumen</button>' : ''}
        </div>`;
    }

    const coverage = insights.coverage || {};
    const probability = Math.round(Number(insights.placement_probability || 0) * 1000) / 10;
    const factors = (insights.top_factors || []).map(factor =>
      `<li>${escapeMarkup(INSIGHT_LABELS[factor.feature] || factor.feature)} <span style="color:var(--text-soft);">(${escapeMarkup(SOURCE_NAMES[factor.source] || factor.source || 'derived')})</span></li>`
    ).join('');
    const inputs = Object.entries(insights.inputs || {}).map(([key, input]) =>
      `<li>${escapeMarkup(INSIGHT_LABELS[key] || key)}: <strong>${escapeMarkup(formatInsightValue(input.value))}</strong> <span style="color:var(--text-soft);">${escapeMarkup(SOURCE_NAMES[input.source] || input.source)}</span></li>`
    ).join('');

    return `
      <div class="prediction-card">
        <div class="label">Placement estimate</div>
        <div class="value">${probability}%</div>
        <div style="color:var(--text-soft);font-size:12px;">Model estimate, ${escapeMarkup(insights.risk_band || '')}</div>
      </div>
      <div class="prediction-card">
        <div class="label">Inputs used</div>
        <div class="value" style="font-size:15px;">${coverage.lumen ?? 0} Lumen · ${coverage.self_reported ?? 0} yours · ${coverage.imputed ?? 0} default</div>
        <div style="color:var(--text-soft);font-size:12px;">Add your profile below to replace defaults.</div>
      </div>
      <div class="prediction-card">
        <div class="label">Top factors</div>
        <ul>${factors || '<li>None reported</li>'}</ul>
      </div>
      <div class="prediction-card" style="grid-column: 1 / -1;">
        <div class="label">Inputs</div>
        <ul style="columns: 2;">${inputs}</ul>
        <div style="color:var(--text-soft);font-size:12px;margin-top:8px;">${escapeMarkup(insights.disclaimer || '')}</div>
      </div>`;
  }

  function renderProfileForm() {
    const fields = PROFILE_FIELDS.map(field => {
      const value = studentProfile[field.key];
      return `
        <label style="display:flex;flex-direction:column;gap:4px;font-size:12px;color:var(--text-soft);">
          ${escapeMarkup(field.label)}
          <input name="${field.key}" type="number" min="${field.min}" max="${field.max}" step="${field.integer ? 1 : 'any'}"
            value="${value === undefined || value === null ? '' : escapeMarkup(value)}"
            style="padding:8px;border:1px solid #d0d7de;border-radius:8px;font-size:13px;">
        </label>`;
    }).join('');
    return `
      <form id="studentProfileForm" class="prediction-card" style="grid-column: 1 / -1;">
        <div class="label">Your profile (optional)</div>
        <div style="color:var(--text-soft);font-size:12px;margin-bottom:10px;">These are not in Lumen. Leave blank to use the default value.</div>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;">${fields}</div>
        <div style="display:flex;align-items:center;gap:10px;margin-top:12px;">
          <button type="submit" class="reset-btn">Save and update estimate</button>
          <span id="profileStatus" style="font-size:12px;color:var(--text-soft);"></span>
        </div>
      </form>`;
  }

  function formatInsightValue(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return '-';
    return Number.isInteger(number) ? String(number) : number.toFixed(2);
  }

  async function loadStudentProfile() {
    if (!auth || !auth.currentUser) return;
    studentProfileLoaded = true;
    try {
      const headers = await getFirebaseAuthHeaders();
      const [profileResponse, insightsResponse] = await Promise.all([
        fetch(`${BACKEND_API_URL}/api/students/me/profile`, { headers }),
        fetch(`${BACKEND_API_URL}/api/students/me/insights`, { headers })
      ]);
      if (profileResponse.ok) studentProfile = (await profileResponse.json()).profile || {};
      if (insightsResponse.ok) predictionInsights = await insightsResponse.json();
      renderPrediction();
    } catch (err) {
      studentProfileLoaded = false;
      console.warn('Could not load prediction profile.', err);
    }
  }

  async function onProfileSubmit(event) {
    if (event.target.id !== 'studentProfileForm') return;
    event.preventDefault();
    const form = event.target;
    const status = document.getElementById('profileStatus');
    const payload = {};
    for (const field of PROFILE_FIELDS) {
      const raw = form.elements[field.key].value.trim();
      if (raw === '') continue;
      const value = Number(raw);
      if (!Number.isFinite(value) || value < field.min || value > field.max) {
        status.textContent = `${field.label} must be between ${field.min} and ${field.max}.`;
        return;
      }
      payload[field.key] = field.integer ? Math.round(value) : value;
    }

    status.textContent = 'Saving…';
    try {
      const headers = { ...(await getFirebaseAuthHeaders()), 'Content-Type': 'application/json' };
      const response = await fetch(`${BACKEND_API_URL}/api/students/me/profile`, {
        method: 'PUT',
        headers,
        body: JSON.stringify(payload)
      });
      if (!response.ok) throw new Error(`server responded ${response.status}`);
      const body = await response.json();
      studentProfile = body.profile || {};
      predictionInsights = body.insights || null;
      renderPrediction();
      const freshStatus = document.getElementById('profileStatus');
      if (freshStatus) freshStatus.textContent = 'Saved.';
    } catch (err) {
      status.textContent = 'Could not save: ' + err.message;
    }
  }

  function renderFilters() {
    const row = document.getElementById('filterRow');
    let html = `<button class="filter-pill ${activeFilter === 'all' ? 'active' : ''}" data-filter="all">All courses</button>`;
    COURSES.forEach(c => {
      html += `<button class="filter-pill ${activeFilter === c.id ? 'active' : ''}" data-filter="${c.id}">${c.name}</button>`;
    });
    row.innerHTML = html;
    row.querySelectorAll('.filter-pill').forEach(btn => {
      btn.addEventListener('click', () => {
        activeFilter = btn.dataset.filter;
        render();
      });
    });
  }

  function renderCourses() {
    const container = document.getElementById('courseContainer');
    const visibleCourses = activeFilter === 'all' ? COURSES : COURSES.filter(c => c.id === activeFilter);
    let html = '';

    visibleCourses.forEach(course => {
      const r = courseCompletion(course);
      const isOpen = openSections[course.id];

      html += `
        <div class="course-section">
          <div class="course-header" data-toggle="${course.id}">
            <div class="course-header-left">
              <div class="course-dot" style="background:${course.color}"></div>
              <div>
                <div class="course-name">${course.name}</div>
                <div class="course-meta">${course.credits}${course.presenter ? ` · Presented by ${course.presenter}` : ''}</div>
              </div>
            </div>
            <div class="course-header-right">
              <div class="course-progress-text">${r.done}/${r.total}</div>
              <div class="course-progress-bar">
                <div class="course-progress-fill" style="width:${r.pct}%; background:${course.color};"></div>
              </div>
              <div class="chevron ${isOpen ? 'open' : ''}">${chevronSvg}</div>
            </div>
          </div>
          ${renderLumenCourseProgress(course)}
          <div class="week-list ${isOpen ? 'open' : ''}">
            ${course.weeks.map(w => renderWeekRow(course, w)).join('')}
          </div>
        </div>
      `;
    });

    container.innerHTML = html;

    container.querySelectorAll('.course-header').forEach(h => {
      h.addEventListener('click', () => {
        const id = h.dataset.toggle;
        openSections[id] = !openSections[id];
        renderCourses();
      });
    });

    container.querySelectorAll('.week-check').forEach(chk => {
      chk.addEventListener('click', (e) => {
        e.stopPropagation();
        const [courseId, weekN] = chk.dataset.toggleweek.split('|');
        toggleStudied(courseId, parseInt(weekN));
      });
    });

    container.querySelectorAll('.module-row').forEach(row => {
      row.addEventListener('click', (e) => {
        e.stopPropagation();
        toggleModule(row.dataset.course, parseInt(row.dataset.week), parseInt(row.dataset.mod));
      });
    });
  }

  function renderLumenCourseProgress(course) {
    const snapshot = buildLumenCourseProgressSnapshot(course);
    const lumenCourse = getLumenCourseForTrackerCourse(course);
    if (!snapshot || !lumenCourse) {
      return `
        <div class="lumen-course-progress">
          <div class="lumen-progress-heading">
            <strong>Lumen progress</strong>
            <span>Sync Lumen to load lecture, quiz, and assignment activity.</span>
          </div>
        </div>
      `;
    }

    const activityTotal = snapshot.activities.length;
    const activityDone = snapshot.activities.filter(activity => activity.completed).length;
    const summaryItems = [
      `${snapshot.lecture_status_available ? 'Lectures viewed' : 'Lumen content complete'} ${snapshot.lectures_viewed}/${snapshot.lectures_total}`,
      `Quizzes completed ${snapshot.quizzes_completed}/${snapshot.quizzes_total}`,
      `Assignments submitted ${snapshot.assignments_submitted}/${snapshot.assignments_total}`
    ];
    const activityRows = snapshot.activities.map(activity => {
      const kindLabel = activity.kind === 'lecture' ? 'Lecture' : activity.kind === 'quiz' ? 'Quiz' : 'Assignment';
      const scoreLabel = activity.score_pct === null || activity.score_pct === undefined
        ? ''
        : ` · ${Number(activity.score_pct).toFixed(1)}%`;
      return `
        <li class="${activity.completed ? 'is-complete' : ''}">
          <span class="lumen-activity-title">${kindLabel}: ${escapeMarkup(activity.title)}</span>
          <span class="lumen-activity-status">${escapeMarkup(activity.status)}${scoreLabel}</span>
        </li>
      `;
    }).join('');
    const syncedLabel = snapshot.last_synced_at ? `Synced ${fmtDate(snapshot.last_synced_at)}` : 'Synced from Lumen';

    return `
      <div class="lumen-course-progress">
        <div class="lumen-progress-heading">
          <strong>Lumen course activity</strong>
          <span>${escapeMarkup(syncedLabel)} · ${snapshot.completion_pct}%</span>
        </div>
        <div class="lumen-progress-bar" role="progressbar" aria-label="${escapeMarkup(course.name)} Lumen activity completion" aria-valuenow="${snapshot.completion_pct}" aria-valuemin="0" aria-valuemax="100">
          <div class="lumen-progress-fill" style="width:${snapshot.completion_pct}%"></div>
        </div>
        <div class="lumen-progress-counts">${summaryItems.map(item => `<span>${item}</span>`).join('')}</div>
        <details class="lumen-activity-details">
          <summary>${snapshot.lecture_status_available
            ? `View ${activityTotal} Lumen activities (${activityDone} complete)`
            : `View ${activityTotal} Lumen activities (lecture status unavailable)`}</summary>
          <ul class="lumen-activity-list">${activityRows || '<li>No lecture, quiz, or assignment activity was returned for this course.</li>'}</ul>
        </details>
      </div>
    `;
  }

  function renderWeekRow(course, week) {
    const studied = isWeekStudied(course, week);
    const status = weekStatus(course, week);
    const modCount = getWeekModulesCount(course, week);
    const doneCount = getWeekDoneCount(course, week);

    let tagHtml = '';
    if (status === 'studied') {
      tagHtml = `<span class="week-status-tag" style="color:var(--done); background:var(--done-bg);">Studied</span>`;
    } else if (status === 'upcoming') {
      tagHtml = `<span class="week-status-tag" style="color:var(--text-faint); background:#f1f2f4;">Upcoming</span>`;
    } else if (status === 'partial') {
      tagHtml = `<span class="week-status-tag" style="color:var(--upcoming); background:var(--upcoming-bg);">${doneCount}/${modCount} done</span>`;
    } else {
      tagHtml = `<span class="week-status-tag" style="color:var(--overdue); background:var(--overdue-bg);">Pending</span>`;
    }

    const syllabusHtml = (week.syllabus && week.syllabus.length)
      ? `<ul class="week-syllabus">${week.syllabus.map((s, idx) => {
          const checked = getModuleState(course.id, week.n, idx);
          const moduleLabel = week.caseStudy && /use case overview/i.test(s)
            ? `Case study overview: ${week.caseStudy}`
            : s;
          return `
            <li class="module-row" data-course="${course.id}" data-week="${week.n}" data-mod="${idx}">
              <div class="module-check ${checked ? 'checked' : ''}" style="${checked ? `background:${course.color}; border-color:${course.color};` : ''}">${checkSvg}</div>
              <span class="module-label ${checked ? 'checked-text' : ''}">${moduleLabel}</span>
            </li>
          `;
        }).join('')}</ul>`
      : '';

    return `
      <div class="week-row ${studied ? 'studied' : ''}">
        <div class="week-check ${studied ? 'checked' : ''}" data-toggleweek="${course.id}|${week.n}" style="${studied ? `background:${course.color}; border-color:${course.color};` : ''}">
          ${checkSvg}
        </div>
        <div class="week-num">Week ${week.label || week.n}</div>
        <div class="week-info">
          <div class="week-topic">${week.topic}</div>
          <div class="week-date">${fmtDate(week.date)}</div>
          ${syllabusHtml}
        </div>
        ${tagHtml}
      </div>
    `;
  }

  function renderDeadlines() {
    const grid = document.getElementById('deadlineGrid');
    let html = '';
    DEADLINES.forEach(dl => {
      const state = deadlineState(dl.date);
      let tagColor = 'var(--text-faint)', tagBg = '#f1f2f4';
      if (state === 'past') { tagColor = 'var(--text-faint)'; tagBg = '#f1f2f4'; }
      if (state === 'soon') { tagColor = 'var(--overdue)'; tagBg = 'var(--overdue-bg)'; }
      if (state === 'future') { tagColor = 'var(--upcoming)'; tagBg = 'var(--upcoming-bg)'; }

      html += `
        <div class="deadline-card">
          <div class="dl-left">
            <div class="dl-title">${dl.title}</div>
            <div class="dl-sub">${dl.sub}</div>
          </div>
          <div class="dl-date-tag" style="color:${tagColor}; background:${tagBg};">${fmtDate(dl.date)}</div>
        </div>
      `;
    });
    grid.innerHTML = html;
  }

  // --- Analytics/Charts Section ---
  let analyticsCharts = {};

  // ── POST TO TIMELINE ──────────────────────────────────────────────────────

  const TL_STORAGE_KEY = 'academos_timeline_cards_v1';

  // ---------- localStorage helpers ----------

  function tlLoadCards() {
    try {
      return JSON.parse(localStorage.getItem(TL_STORAGE_KEY) || '[]');
    } catch { return []; }
  }

  function tlSaveCard(entry) {
    // entry = { id, dataURL, userName, ts, overallPct, savedAt }
    const cards = tlLoadCards();
    cards.unshift(entry);                   // newest first
    // Keep only the 10 most recent to avoid filling localStorage
    const trimmed = cards.slice(0, 10);
    try {
      localStorage.setItem(TL_STORAGE_KEY, JSON.stringify(trimmed));
      return true;
    } catch (e) {
      // Storage quota exceeded — drop oldest and retry once
      try {
        localStorage.setItem(TL_STORAGE_KEY, JSON.stringify(trimmed.slice(0, 5)));
        return true;
      } catch { return false; }
    }
  }

  function tlDeleteCard(id) {
    const cards = tlLoadCards().filter(c => c.id !== id);
    localStorage.setItem(TL_STORAGE_KEY, JSON.stringify(cards));
  }

  // ---------- Main entry point ----------

  document.getElementById('postTimelineBtn').addEventListener('click', buildTimelinePost);

  async function buildTimelinePost() {
    const btn = document.getElementById('postTimelineBtn');
    btn.classList.add('loading');
    btn.innerHTML = `
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="animation:spin 0.9s linear infinite;">
        <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
      </svg>
      Generating…`;

    try {
      // --- Build data snapshot ---
      const overall = overallCompletion();
      const courseData = COURSES.map(c => {
        const r = courseCompletion(c);
        return { ...c, pct: r.pct, done: r.done, total: r.total };
      });

      const now      = new Date();
      const ts       = now.toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric' });
      const userName = (currentUser && currentUser.displayName)
        ? currentUser.displayName
        : (currentUser && currentUser.email ? currentUser.email.split('@')[0] : 'Student');

      // --- Grab the two live Chart.js canvases directly (synchronous, no html2canvas) ---
      const srcBar  = document.getElementById('courseProgressChart');
      const srcLine = document.getElementById('weeklyCompletionChart');
      if (!srcBar || !srcLine) throw new Error('Charts not rendered yet.');

      const dataURL = compositeChartCard(srcBar, srcLine, userName, ts);

      // ① Persist to localStorage
      const cardEntry = {
        id:      `tl_${Date.now()}`,
        dataURL,
        fileName: `academic-os-charts-${userName.replace(/\s+/g, '-').toLowerCase()}-${Date.now()}.png`,
        userName,
        ts,
        savedAt: now.toISOString(),
      };
      const saved = tlSaveCard(cardEntry);

      // ② Show preview modal immediately (no async wait)
      showTimelinePreview(dataURL, userName, ts, cardEntry.id, cardEntry.fileName, saved);

    } catch (err) {
      console.error('Timeline snapshot failed:', err);
      alert('Could not generate the progress card. Please try again.');
    } finally {
      btn.classList.remove('loading');
      btn.innerHTML = `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/>
        </svg>
        Post to Timeline`;
    }
  }

  function _triggerDownload(dataURL, fileName) {
    const a = document.createElement('a');
    a.href = dataURL;
    a.download = fileName;
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    setTimeout(() => document.body.removeChild(a), 200);
  }

  // ---------- Chart compositor ----------
  // Reads the two live Chart.js canvases directly via toDataURL() — synchronous,
  // no html2canvas, no off-screen DOM card.  Produces a professional dark-framed
  // PNG with only the two charts and a minimal brand header/footer.

  function compositeChartCard(srcBar, srcLine, userName, ts) {
    const S      = 2;             // retina scale
    const PAD    = 44 * S;        // outer padding (left/right of card)
    const GAP    = 48 * S;        // gap BETWEEN the two chart cards
    const HDRH   = 68 * S;        // header height
    const FTRH   = 46 * S;        // footer height
    const LBLH   = 24 * S;        // label row height above each chart
    const R      = 14 * S;        // outer card corner radius
    const INSET  = 14 * S;        // padding inside each white chart card
    const CARD_R = 12 * S;        // white card corner radius

    // Source canvas rendered sizes
    const chartW = (srcBar.offsetWidth  || 480) * S;
    const chartH = (srcBar.offsetHeight || 250) * S;

    // Each white card is the chart + inset on all four sides
    const cardW  = chartW + INSET * 2;
    const cardH  = chartH + INSET * 2;

    const totalW = PAD + cardW + GAP + cardW + PAD;
    const totalH = HDRH + PAD + LBLH + cardH + PAD + FTRH;

    const out = document.createElement('canvas');
    out.width  = totalW;
    out.height = totalH;
    const ctx  = out.getContext('2d');

    // ── Background ─────────────────────────────────────────────────────────
    ctx.fillStyle = '#0f1117';
    rrect(ctx, 0, 0, totalW, totalH, R); ctx.fill();

    // Subtle top glow
    const grd = ctx.createLinearGradient(0, 0, 0, HDRH * 2);
    grd.addColorStop(0, 'rgba(255,255,255,0.05)');
    grd.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = grd;
    rrect(ctx, 0, 0, totalW, totalH, R); ctx.fill();

    // ── Header ─────────────────────────────────────────────────────────────
    ctx.fillStyle = 'rgba(255,255,255,0.03)';
    rrectTop(ctx, 0, 0, totalW, HDRH, R); ctx.fill();

    ctx.strokeStyle = 'rgba(255,255,255,0.07)';
    ctx.lineWidth   = 1;
    ctx.beginPath(); ctx.moveTo(0, HDRH); ctx.lineTo(totalW, HDRH); ctx.stroke();

    ctx.fillStyle    = 'rgba(255,255,255,0.88)';
    ctx.font         = `700 ${15 * S}px Inter,-apple-system,sans-serif`;
    ctx.textBaseline = 'middle';
    ctx.fillText('Academic OS  ·  Learning Analytics', PAD, HDRH / 2);

    ctx.fillStyle = 'rgba(255,255,255,0.28)';
    ctx.font      = `500 ${11 * S}px Inter,-apple-system,sans-serif`;
    const dw = ctx.measureText(ts).width;
    ctx.fillText(ts, totalW - PAD - dw, HDRH / 2);

    // ── Card positions ──────────────────────────────────────────────────────
    const card1X  = PAD;                       // left card X
    const card2X  = PAD + cardW + GAP;         // right card X
    const lblY    = HDRH + PAD;               // top of label row
    const cardY   = lblY + LBLH;              // top of white cards
    const chartY  = cardY + INSET;            // chart draw origin Y (inside card)

    // ── Labels (aligned to card left edge) ─────────────────────────────────
    ctx.fillStyle    = 'rgba(255,255,255,0.32)';
    ctx.font         = `700 ${9 * S}px Inter,-apple-system,sans-serif`;
    ctx.textBaseline = 'alphabetic';
    ctx.fillText('COURSE COMPLETION', card1X, lblY + LBLH * 0.78);
    ctx.fillText('MODULES BY COURSE',  card2X, lblY + LBLH * 0.78);

    // ── White cards + charts ────────────────────────────────────────────────
    [[srcBar, card1X], [srcLine, card2X]].forEach(([src, cx]) => {
      // White card background
      ctx.fillStyle = 'rgba(255,255,255,0.97)';
      rrect(ctx, cx, cardY, cardW, cardH, CARD_R);
      ctx.fill();
      // Draw live canvas — synchronous canvas-to-canvas, always ready
      ctx.drawImage(src, cx + INSET, chartY, chartW, chartH);
    });

    // ── Footer ─────────────────────────────────────────────────────────────
    const ftrY = totalH - FTRH;
    ctx.strokeStyle = 'rgba(255,255,255,0.06)';
    ctx.lineWidth   = 1;
    ctx.beginPath(); ctx.moveTo(0, ftrY); ctx.lineTo(totalW, ftrY); ctx.stroke();

    ctx.fillStyle    = 'rgba(255,255,255,0.18)';
    ctx.font         = `600 ${10 * S}px Inter,-apple-system,sans-serif`;
    ctx.textBaseline = 'middle';
    ctx.fillText('academic-os.bitspilani.ac.in', PAD, ftrY + FTRH / 2);

    ctx.fillStyle = 'rgba(255,255,255,0.18)';
    ctx.font      = `500 ${10 * S}px Inter,-apple-system,sans-serif`;
    const uw = ctx.measureText(userName).width;
    ctx.fillText(userName, totalW - PAD - uw, ftrY + FTRH / 2);

    return out.toDataURL('image/png');
  }

  // Rounded-rect path helpers (no Path2D — Safari < 15.4 compat)
  function rrect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);   ctx.quadraticCurveTo(x + w, y,     x + w, y + r);
    ctx.lineTo(x + w, y + h - r); ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h);   ctx.quadraticCurveTo(x,     y + h, x,     y + h - r);
    ctx.lineTo(x, y + r);       ctx.quadraticCurveTo(x,     y,     x + r, y);
    ctx.closePath();
  }

  function rrectTop(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y); ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h);
    ctx.lineTo(x, y + h);
    ctx.lineTo(x, y + r);     ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.closePath();
  }

  function showTimelinePreview(dataURL, userName, ts, savedCardId, fileName, wasSaved) {
    const overlay = document.createElement('div');
    overlay.className = 'tl-preview-overlay';

    // Saved-cards thumbnail gallery (excludes the card just saved, shown as main preview)
    const allCards  = tlLoadCards();
    const prevCards = allCards.filter(c => c.id !== savedCardId);
    const galleryHTML = prevCards.length ? `
      <div class="tl-saved-section">
        <div class="tl-saved-header">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:13px;height:13px;flex-shrink:0;">
            <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/>
          </svg>
          Previous snapshots (${prevCards.length})
        </div>
        <div class="tl-saved-grid">
          ${prevCards.map(c => `
            <div class="tl-saved-thumb">
              <img src="${c.dataURL}" alt="Snapshot from ${c.ts}">
              <div class="tl-saved-thumb-meta"><span>${c.ts}</span></div>
              <div class="tl-saved-thumb-actions">
                <button class="tl-thumb-dl" data-url="${c.dataURL}" data-file="${c.fileName || 'charts.png'}" title="Download">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                </button>
                <button class="tl-thumb-del" data-id="${c.id}" title="Delete">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4h6v2"/></svg>
                </button>
              </div>
            </div>
          `).join('')}
        </div>
      </div>` : '';

    overlay.innerHTML = `
      <div class="tl-preview-modal">
        <div class="tl-preview-top">
          <div>
            <h3>Your Charts Snapshot</h3>
            <p>Captured from your live progress charts &middot; Ready to share when Timeline launches.</p>
          </div>
          <span class="tl-coming-soon-chip">Timeline coming soon</span>
        </div>

        <div class="tl-saved-banner${wasSaved ? '' : ' tl-saved-banner--warn'}">
          ${wasSaved
            ? `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="width:13px;height:13px;flex-shrink:0;"><polyline points="20 6 9 17 4 12"/></svg>
               Saved to browser &middot; ${allCards.length} card${allCards.length !== 1 ? 's' : ''} stored
               <button class="tl-banner-clear" id="tlClearAllBtn">Clear all</button>`
            : `Storage full &mdash; could not save. Download still completed.`
          }
        </div>

        <div class="tl-preview-img-wrap">
          <img src="${dataURL}" alt="Progress card preview">
        </div>

        ${galleryHTML}

        <div class="tl-preview-actions">
          <button class="tl-action-btn secondary" id="tlCloseBtn">Close</button>
          <button class="tl-action-btn secondary" id="tlCopyBtn">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
            </svg>
            Copy image
          </button>
          <button class="tl-action-btn primary" id="tlDownloadAgainBtn">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
            Download again
          </button>
        </div>
      </div>
    `;

    document.body.appendChild(overlay);

    // Close handlers
    overlay.querySelector('#tlCloseBtn').addEventListener('click', () => document.body.removeChild(overlay));
    overlay.addEventListener('click', e => { if (e.target === overlay) document.body.removeChild(overlay); });

    // Download again
    overlay.querySelector('#tlDownloadAgainBtn').addEventListener('click', () => {
      _triggerDownload(dataURL, fileName || `academic-os-charts-${Date.now()}.png`);
    });

    // Copy to clipboard
    overlay.querySelector('#tlCopyBtn').addEventListener('click', async () => {
      const copyBtn = overlay.querySelector('#tlCopyBtn');
      try {
        const res  = await fetch(dataURL);
        const blob = await res.blob();
        await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
        copyBtn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg> Copied!`;
        setTimeout(() => {
          copyBtn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> Copy image`;
        }, 2000);
      } catch { copyBtn.innerText = 'Copy not supported'; }
    });

    // Clear all
    const clearBtn = overlay.querySelector('#tlClearAllBtn');
    if (clearBtn) {
      clearBtn.addEventListener('click', () => {
        localStorage.removeItem(TL_STORAGE_KEY);
        document.body.removeChild(overlay);
      });
    }

    // Per-thumb download
    overlay.querySelectorAll('.tl-thumb-dl').forEach(btn => {
      btn.addEventListener('click', e => {
        e.stopPropagation();
        _triggerDownload(btn.dataset.url, btn.dataset.file);
      });
    });

    // Per-thumb delete
    overlay.querySelectorAll('.tl-thumb-del').forEach(btn => {
      btn.addEventListener('click', e => {
        e.stopPropagation();
        tlDeleteCard(btn.dataset.id);
        btn.closest('.tl-saved-thumb').remove();
        const remaining = tlLoadCards().filter(c => c.id !== savedCardId).length;
        const hdr = overlay.querySelector('.tl-saved-header');
        if (hdr) hdr.lastChild.textContent = ` Previous cards (${remaining})`;
        if (remaining === 0) {
          const sec = overlay.querySelector('.tl-saved-section');
          if (sec) sec.remove();
        }
      });
    });
  }

  // ── ANALYTICS ──────────────────────────────────────────────────────────────

  function renderAnalytics() {
    if (typeof Chart === 'undefined') return;

    Object.values(analyticsCharts).forEach(chart => chart.destroy());
    analyticsCharts = {};
    if (!COURSES.length) return;

    const progressCtx = document.getElementById('courseProgressChart');
    const weeklyCtx = document.getElementById('weeklyCompletionChart');
    if (!progressCtx || !weeklyCtx) return;

    analyticsCharts.progress = new Chart(progressCtx, {
      type: 'bar',
      data: {
        labels: COURSES.map(c => c.name),
        datasets: [{
          label: 'Completion %',
          data: COURSES.map(c => courseCompletion(c).pct)
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          title: { display: true, text: 'Course Completion' }
        },
        scales: {
          x: {
            ticks: {
              autoSkip: false,
              maxRotation: 0,
              minRotation: 0,
              callback: function(value) {
                const labels = COURSES.map(c => c.name);
                return labels[value];
              }
            }
          },
          y: {
            beginAtZero: true,
            max: 100
          }
        }
      }
    });

    analyticsCharts.weekly = new Chart(weeklyCtx, {
      type: 'line',
      data: {
        labels: COURSES.map(c => c.id.toUpperCase()),
        datasets: [{
          label: 'Modules Completed',
          data: COURSES.map(c => courseCompletion(c).done),
          tension: 0.35
        }]
      },
      options: {
        responsive: true,
        plugins: { title: { display: true, text: 'Completed Modules by Course' } }
      }
    });
  }
