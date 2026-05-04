# Real-Time Login Anomaly Detection System

A professional behavioral biometrics system for detecting account takeover attempts using machine learning. Built for Black Hat conference demonstration.

## 🎯 Features

### High-Impact Capabilities
- **Ensemble ML Model**: IsolationForest + One-Class SVM + LSTM Autoencoder
- **30+ Behavioral Features**: Mouse, keystroke, temporal, navigation, and cross-modal analysis
- **Real-Time Detection**: Live behavioral monitoring and risk assessment
- **Interactive Dashboard**: Session replay, risk visualization, and statistics
- **Professional Architecture**: Clean, modular, production-ready code

### Detection Capabilities
- Mouse movement patterns (velocity, acceleration, jerk, curvature)
- Keystroke dynamics (dwell time, flight time, typing rhythm)
- Temporal patterns (time of day, session evolution)
- Navigation behavior (page transitions, scroll patterns)
- Cross-modal analysis (mouse-keyboard coordination)

## 📁 Project Structure

```
lato-lato/
├── server/                 # Backend API
│   ├── models/            # ML models
│   ├── app.py             # Flask API
│   ├── config.py          # Configuration
│   ├── schemas.py         # Data validation
│   ├── database.py        # Database operations
│   ├── feature_extraction.py  # Feature engineering
│   ├── risk_engine.py     # Risk scoring
│   └── pipeline.py        # Real-time processing
├── web/                   # Frontend
│   ├── static/
│   │   ├── css/          # Stylesheets
│   │   └── js/           # JavaScript
│   └── templates/        # HTML templates
├── model/                # Trained models
├── data/                 # Session data
├── logs/                 # Application logs
├── requirements.txt
├── run.py
└── README.md
```

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the Application

```bash
python run.py
```

The server will start on `http://127.0.0.1:5000`

### 3. Access the Application

- **Login Page**: http://127.0.0.1:5000/
- **Dashboard**: http://127.0.0.1:5000/dashboard

## 📖 Usage Guide

### Step 1: Register and Login

1. Open the application in your browser
2. Click "Register" to create a new account
3. Login with your credentials

### Step 2: Collect Training-Valid Sessions

1. Login and browse the `shop`, `cart`, `checkout`, or `wallet` pages naturally
2. A session becomes **valid for training** when it is ended and contains at least **30 behavioral events**
3. Use natural typing, scrolling, and mouse movements across the flow
4. Collect several completed sessions before training a model

### Step 3: Train the Model

1. Open **Dashboard**
2. Click **Train Model**
3. Choose **global** or **personal** scope, feature subset, and minimum sample count
4. Wait for training confirmation

### Step 4: Monitor for Anomalies

1. Continue using the system normally
2. The system will automatically detect anomalous behavior
3. Risk levels: **LOW** (allow), **MEDIUM** (require MFA), **HIGH** (block)
4. Lower anomaly scores are riskier: `< 0.0 = HIGH`, `0.0 - 0.5 = MEDIUM`, `> 0.5 = LOW`

### Step 5: View Dashboard

1. Click "Dashboard" to view statistics
2. See session replay, risk distribution, and top users
3. Load any session ID to replay mouse trajectory

## 🔧 Configuration

Edit `server/config.py` to customize:

- **Model parameters**: Contamination, estimators, sequence length
- **Risk thresholds**: Low/Medium/High risk boundaries
- **Pipeline settings**: Rolling window size, assessment intervals
- **Database paths**: SQLite database location

## 🧪 Testing Anomaly Detection

To test the anomaly detection:

1. **Normal behavior**: Use your natural typing rhythm and mouse movements
2. **Anomalous behavior**:
   - Type much faster/slower than usual
   - Make erratic mouse movements
   - Use different navigation patterns
   - Copy/paste frequently

## 📊 API Endpoints

### Authentication
- `POST /api/v1/register` - Register new user
- `POST /api/v1/login` - User login

### Sessions
- `POST /api/v1/sessions/start` - Start new session
- `POST /api/v1/events` - Submit behavioral events
- `POST /api/v1/sessions/assess` - Get risk assessment
- `POST /api/v1/sessions/{id}/end` - End session
- `POST /api/v1/sessions/{id}/force-end` - Force-end a session from database UI

### Model & Dashboard
- `POST /api/v1/model/train` - Train anomaly detection model
- `GET /api/v1/users` - List users for personal model training
- `GET /api/v1/models/options` - List available reassessment models
- `GET /api/v1/dashboard/stats` - Get dashboard statistics
- `GET /api/v1/sessions/{id}/replay` - Get session replay data
- `POST /api/v1/sessions/{id}/reassess` - Re-run risk prediction with selected model

## 🧠 ML Models

### Isolation Forest
- Unsupervised anomaly detection
- Good for high-dimensional data
- Fast training and prediction

### One-Class SVM
- Kernel-based anomaly detection
- Effective for non-linear patterns
- Robust to outliers

### LSTM Autoencoder
- Deep learning approach
- Captures temporal dependencies
- Best for sequence-based patterns

### Ensemble Model
- Combines all three models
- Weighted voting mechanism
- Improved accuracy and robustness

## 🔒 Security Features

- **Password Hashing**: Uses werkzeug security
- **Session Management**: Secure session IDs
- **CORS Protection**: Configured allowed origins
- **Input Validation**: Pydantic schema validation
- **SQL Injection Prevention**: Parameterized queries

## 📈 Performance

- **Real-time processing**: <100ms per event batch
- **Model training**: <5 seconds for 100 samples
- **Memory usage**: ~200MB with models loaded
- **Scalability**: SQLite → PostgreSQL upgrade path

## 🎓 For Black Hat Demo

### Live Demo Tips
1. **Prepare beforehand**: Have several completed training-valid sessions ready
2. **Train model**: Train before the presentation
3. **Test attacks**: Have attack scenarios prepared
4. **Show dashboard**: Demonstrate session replay

### Suggested Attack Demonstrations
1. **Fast typing**: Bot-like typing speed
2. **Erratic mouse**: Unnatural mouse movements
3. **Hybrid attack**: Human login + bot navigation
4. **Replay attack**: Record and replay legitimate session

## 🛠️ Troubleshooting

### Model not trained
- Ensure you have enough completed training-valid sessions
- Check that events were submitted successfully
- Try training with more samples

### High false positive rate
- Increase the number of completed training-valid sessions
- Adjust risk thresholds in config.py
- Ensure natural behavior during data collection

### Dashboard not loading
- Check browser console for errors
- Verify API is running: `GET /api/v1/health`
- Ensure CORS is properly configured

## 📝 Dependencies

```
flask==3.1.3
flask-cors==4.0.0
werkzeug==3.1.0
scikit-learn==1.3.2
numpy==1.24.3
pandas==2.0.3
joblib==1.3.2
tensorflow==2.15.0
pydantic==2.5.0
python-dotenv==1.0.0
```

## 🤝 Contributing

This is a research/demo project. For improvements:
1. Follow the existing code style
2. Add tests for new features
3. Update documentation
4. Test thoroughly before changes

## 📄 License

This project is for educational and research purposes.

## 👤 Author

Built for Black Hat conference demonstration on behavioral biometrics and anomaly detection.

## 🙏 Acknowledgments

- scikit-learn for ML algorithms
- TensorFlow for deep learning
- Flask for web framework
- Chart.js for visualizations

---

**Note**: This system is for demonstration purposes. For production use, additional security hardening and testing are required.
