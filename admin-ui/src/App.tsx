import { Routes, Route, Link } from 'react-router-dom';
import { ProjectList } from './components/ProjectList';
import { ProjectDetail } from './components/ProjectDetail';
import { Management } from './components/Management';

function App() {
  return (
    <div className="min-h-screen">
      <Routes>
        <Route path="/" element={<ProjectList />} />
        <Route path="/projects/:id" element={<ProjectDetail />} />
        <Route path="/management" element={<Management />} />
        <Route
          path="*"
          element={
            <div className="min-h-screen flex items-center justify-center p-6">
              <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-6 text-center max-w-md w-full">
                <h1 className="text-xl font-bold text-gray-800 mb-2">页面不存在</h1>
                <p className="text-sm text-gray-500 mb-4">请返回项目列表继续操作。</p>
                <Link to="/" className="inline-flex px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700">
                  返回首页
                </Link>
              </div>
            </div>
          }
        />
      </Routes>
    </div>
  );
}

export default App;
