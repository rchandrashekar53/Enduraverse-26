import shap
import matplotlib.pyplot as plt


def shap_explain(model, X, output_path='data/shap_summary.png'):
    explainer = shap.Explainer(model)
    shap_values = explainer(X)
    shap.summary_plot(shap_values, X, show=False)
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()
    return output_path


def feature_importance(model, X, output_path='data/feature_importance.png'):
    if hasattr(model, 'feature_importances_'):
        import numpy as np
        import pandas as pd
        import matplotlib.pyplot as plt
        fi = model.feature_importances_
        names = X.columns
        df = pd.DataFrame({'feature': names, 'importance': fi}).sort_values('importance', ascending=False)
        plt.figure(figsize=(8, 5))
        plt.barh(df['feature'], df['importance'])
        plt.gca().invert_yaxis()
        plt.xlabel('Importance')
        plt.title('Feature Importance')
        plt.tight_layout()
        plt.savefig(output_path)
        plt.close()
        return output_path
    return None
