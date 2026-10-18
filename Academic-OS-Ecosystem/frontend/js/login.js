// Login page script (extracted from login.html for the extension CSP).
  // ---------- DATA ----------
  const TODAY = new Date('2026-06-20');

  const COURSES = [
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

  const DEADLINES = [
    { date: '2026-06-09', title: 'Quiz 1 deadline', sub: 'Data Preprocessing, Statistical Modelling, Data Visualization' },
    { date: '2026-06-30', title: 'Quiz 2 deadline', sub: 'Data Preprocessing, Statistical Modelling, Data Visualization, and Feature Engineering Quiz 1' },
    { date: '2026-07-21', title: 'Quiz 3 deadline', sub: 'Statistical Modelling, Data Visualization, and Feature Engineering Quiz 2' },
    { date: '2026-08-08', title: 'Assignment deadline, all 4 courses', sub: 'Data Preprocessing, Statistical Modelling, Data Visualization, Feature Engineering' }
  ];

  // ---------- FIREBASE OR MOCK INITIALIZATION ----------
  const LOCAL_OFFLINE_KEY = 'msc_tracker_progress_v2';
  const PRIVATE_STORE_KEY = 'msc_tracker_cloud_sync_v2';

  let db = null;
  let auth = null;
  let appId = 'msc-dsai-tracker';
  let isFirebaseConfigured = false;

  // Initialize Firebase using your project configuration
  const firebaseConfig = {
    apiKey: "AIzaSyCTNPwLzpWNUI7ltQFJtv_E4W3oZQWnflQ",
    authDomain: "bits-dsai-tracker.firebaseapp.com",
    projectId: "bits-dsai-tracker",
    storageBucket: "bits-dsai-tracker.firebasestorage.app",
    messagingSenderId: "530627005818",
    appId: "1:530627005818:web:24ca6180f9ed9e2fcbdac3",
    measurementId: "G-LQWPPG78GS"
  };

  try {
    firebase.initializeApp(firebaseConfig);
    auth = firebase.auth();
    db = firebase.firestore();
    isFirebaseConfigured = true;
    console.log("Firebase App & Auth successfully initialized.");
  } catch (err) {
    console.error("Firebase initialization failed:", err);
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
  let activeFilter = 'all';
  let openSections = {};
  let currentUser = null;
  let isAuthLoading = true;

  // Pre-expand sections
  COURSES.forEach(c => openSections[c.id] = true);

  // ---------- INITIALIZE APP & AUTH LISTENERS ----------
  window.onload = async function() {
    setupAuthDOMListeners();
    
    if (isFirebaseConfigured) {
      // Rule 3: Auth first. Listen to changes
      auth.onAuthStateChanged(async (user) => {
        isAuthLoading = false;
        document.getElementById('appInitLoader').classList.add('hidden');
        
        if (user) {
          currentUser = user;
          // Verify valid domain
          if (isAuthorizedGoogleUser(user)) {
            await initializeUserDashboard(user);
          } else {
            await auth.signOut();
            alert("Sign in with your official BITS Google account to use this application.");
            showAuthPortal();
            return;
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
            await auth.signOut();
            alert("Sign in with your official BITS Google account to use this application.");
            setAuthLoadingState(false);
          }
        }
      } catch (error) {
        console.error("Google Auth failed: ", error);
        showAuthAlert("Google Authentication failed: " + error.message, "error");
        setAuthLoadingState(false);
      }
    });

    // Reset Progress Metrics Trigger
    document.getElementById('resetBtn').addEventListener('click', async () => {
      const confirmReset = await showCustomConfirm("Are you sure you want to reset all tracking progress on this account? This will clear your modules checklist on the Cloud.");
      if (confirmReset) {
        progress = {};
        await syncProgressToCloud();
        render();
      }
    });

    // Sign out trigger
    document.getElementById('signOutBtn').addEventListener('click', async () => {
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
    });
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
    const portal = document.getElementById('authPortal');
    portal.style.display = 'block';
    setAuthLoadingState(false);
  }

  // ---------- USER DASHBOARD LOADER & DATA MIGRATION ----------
  async function initializeUserDashboard(user) {
    document.getElementById('authPortal').style.display = 'none';
    document.getElementById('mainTrackerApp').classList.remove('hidden');
    
    document.getElementById('userBadgeEmail').innerText = user.email || user.displayName || "Authorized Student";
    document.getElementById('userBadgeEmail').title = user.email;

    setSyncState("Fetching Cloud metrics...", true);
    progress = await fetchUserProgressFromCloud(user.uid);
    
    // Merge offline local tracking to the cloud automatically
    const offlineProgressRaw = localStorage.getItem(LOCAL_OFFLINE_KEY);
    if (offlineProgressRaw) {
      try {
        const offlineProgress = JSON.parse(offlineProgressRaw);
        if (Object.keys(offlineProgress).length > 0) {
          let migratedCount = 0;
          for (const courseId in offlineProgress) {
            if (!progress[courseId]) progress[courseId] = {};
            for (const weekNum in offlineProgress[courseId]) {
              if (!progress[courseId][weekNum]) progress[courseId][weekNum] = {};
              for (const modIdx in offlineProgress[courseId][weekNum]) {
                if (offlineProgress[courseId][weekNum][modIdx] && !progress[courseId][weekNum][modIdx]) {
                  progress[courseId][weekNum][modIdx] = true;
                  migratedCount++;
                }
              }
            }
          }
          if (migratedCount > 0) {
            console.info(`Migrated ${migratedCount} metrics from browser offline history into cloud student workspace.`);
            await syncProgressToCloud();
            localStorage.removeItem(LOCAL_OFFLINE_KEY);
          }
        }
      } catch (e) {
        console.warn("Offline migration parse warning: ", e);
      }
    }

    setSyncState("Cloud synced", false);
    render();
  }

  // ---------- CLOUD FIRESTORE DATALAYER ----------
  async function fetchUserProgressFromCloud(userId) {
    if (isFirebaseConfigured) {
      try {
        if (!auth.currentUser) return {};
        const docRef = db.doc(`artifacts/${appId}/users/${userId}/progress/trackerData`);
        const snapshot = await docRef.get();
        if (snapshot.exists) {
          const payload = snapshot.data();
          return payload.progress || {};
        }
      } catch (err) {
        console.error("Firestore loading failure. Working with offline safety cache.", err);
      }
    } else {
      return simulatedDB.progressStore[userId] || {};
    }
    return {};
  }

  async function syncProgressToCloud() {
    if (!currentUser) return;
    
    setSyncState("Syncing data to Cloud...", true);
    
    if (isFirebaseConfigured) {
      try {
        if (!auth.currentUser) return;
        const docRef = db.doc(`artifacts/${appId}/users/${currentUser.uid}/progress/trackerData`);
        await docRef.set({
          progress: progress,
          updatedAt: firebase.firestore.FieldValue.serverTimestamp()
        }, { merge: true });
        setSyncState("Metrics saved securely in Cloud", false);
      } catch (err) {
        console.error("Firestore sync metrics error: ", err);
        setSyncState("Sync offline - auto retrying", false);
      }
    } else {
      simulatedDB.progressStore[currentUser.uid] = progress;
      simulatedDB.save();
      setSyncState("Metrics saved offline", false);
    }
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
    const d = new Date(iso);
    return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
  }

  function weekStatus(course, week) {
    const studied = isWeekStudied(course, week);
    if (studied) return 'studied';
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
    renderSummary();
    renderPrediction();
    renderFilters();
    renderCourses();
    renderDeadlines();
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

  function renderPrediction() {
    const grid = document.getElementById('predictionGrid');
    const overall = overallCompletion().pct;

    const expected = overall >= 80 ? 'Excellent' : overall >= 60 ? 'Good' : overall >= 40 ? 'Average' : 'Needs Improvement';
    const probability = Math.min(98, Math.max(25, overall + 10));
    const risk = overall >= 80 ? 'Low' : overall >= 60 ? 'Moderate' : 'High';
    const consistency = overall >= 80 ? 'Very High' : overall >= 60 ? 'High' : overall >= 40 ? 'Medium' : 'Low';
    const studyTime = overall >= 80 ? '1.5–2 hrs/day' : overall >= 60 ? '2–3 hrs/day' : '3–4 hrs/day';

    grid.innerHTML = `
      <div class="prediction-card">
        <div class="label">Expected Performance</div>
        <div class="value">${expected}</div>
      </div>

      <div class="prediction-card">
        <div class="label">Probability</div>
        <div class="value">${probability}%</div>
        <div style="color:var(--text-soft);font-size:12px;">Chance of achieving expected outcome</div>
      </div>

      <div class="prediction-card">
        <div class="label">Risk</div>
        <div class="value">${risk}</div>
        <div style="color:var(--text-soft);font-size:12px;">Based on current progress</div>
      </div>

      <div class="prediction-card">
        <div class="label">Consistency</div>
        <div class="value">${consistency}</div>
      </div>

      <div class="prediction-card">
        <div class="label">Recommended Study Time</div>
        <div class="value">${studyTime}</div>
      </div>

      <div class="prediction-card">
        <div class="label">Top Factors</div>
        <ul>
          <li>Course completion</li>
          <li>Weekly consistency</li>
          <li>Module completion rate</li>
          <li>Pending syllabus</li>
          <li>Study momentum</li>
        </ul>
      </div>
    `;
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
                <div class="course-meta">${course.credits}</div>
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
          return `
            <li class="module-row" data-course="${course.id}" data-week="${week.n}" data-mod="${idx}">
              <div class="module-check ${checked ? 'checked' : ''}" style="${checked ? `background:${course.color}; border-color:${course.color};` : ''}">${checkSvg}</div>
              <span class="module-label ${checked ? 'checked-text' : ''}">${s}</span>
            </li>
          `;
        }).join('')}</ul>`
      : '';

    return `
      <div class="week-row ${studied ? 'studied' : ''}">
        <div class="week-check ${studied ? 'checked' : ''}" data-toggleweek="${course.id}|${week.n}" style="${studied ? `background:${course.color}; border-color:${course.color};` : ''}">
          ${checkSvg}
        </div>
        <div class="week-num">Week ${week.n}</div>
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
