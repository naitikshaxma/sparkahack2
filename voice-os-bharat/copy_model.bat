@echo off
echo Creating models directory...
mkdir "C:\Users\sharm\OneDrive\Desktop\voiceos\voice-os-bharat\ml_service\models\multilingual_intent_model" 2>nul
echo.
echo Copying model files...
xcopy "C:\Users\sharm\Downloads\multilingual_intent_model (1)\*" "C:\Users\sharm\OneDrive\Desktop\voiceos\voice-os-bharat\ml_service\models\multilingual_intent_model" /E /H /C /I /Y
echo.
echo =========================================
echo Done! Model copied to ml_service/models/
echo =========================================
pause
