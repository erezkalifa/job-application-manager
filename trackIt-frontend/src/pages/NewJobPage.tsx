import React, { useState } from "react";
import styled from "styled-components";
import { useNavigate } from "react-router-dom";
import {
  FaBriefcase,
  FaFileAlt,
  FaCloudUploadAlt,
  FaEye,
  FaDownload,
  FaTrash,
  FaFolder,
} from "react-icons/fa";
import { JobStatus } from "../types/types";
import { api } from "../api/config";
import { useJobs } from "../context/JobContext";

const PageContainer = styled.div`
  padding: 2rem;
  display: grid;
  grid-template-columns: minmax(350px, 2fr) minmax(600px, 3fr);
  gap: 2rem;
`;

const CardContainer = styled.div`
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 16px;
  padding: 2rem;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
  height: fit-content;
`;

const CardHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 2rem;
  color: ${({ theme }) => theme.colors.text};

  svg {
    font-size: 1.5rem;
    opacity: 0.8;
  }

  h2 {
    font-size: 1.5rem;
    font-weight: 600;
    margin: 0;
  }
`;

const FormGroup = styled.div`
  margin-bottom: 1.5rem;

  label {
    display: block;
    font-size: 0.9375rem;
    font-weight: 500;
    color: ${({ theme }) => theme.colors.textLight};
    margin-bottom: 0.75rem;
  }
`;

const Input = styled.input`
  width: 100%;
  padding: 0.75rem;
  font-size: 0.9375rem;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  color: ${({ theme }) => theme.colors.text};
  transition: all 0.2s ease;

  &:hover,
  &:focus {
    border-color: rgba(255, 255, 255, 0.2);
    background: rgba(255, 255, 255, 0.08);
    outline: none;
  }
`;

const Select = styled.select`
  width: 100%;
  padding: 0.75rem;
  font-size: 0.9375rem;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  color: ${({ theme }) => theme.colors.text};
  cursor: pointer;
  transition: all 0.2s ease;

  &:hover,
  &:focus {
    border-color: rgba(255, 255, 255, 0.2);
    background: rgba(255, 255, 255, 0.08);
    outline: none;
  }

  option {
    background: white;
    color: #1a1a1a;
    padding: 12px;
    font-size: 0.9375rem;
    line-height: 1.5;
  }
`;

const TextArea = styled.textarea`
  width: 100%;
  padding: 0.75rem;
  font-size: 0.9375rem;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  color: ${({ theme }) => theme.colors.text};
  min-height: 100px;
  resize: vertical;
  transition: all 0.2s ease;

  &:hover,
  &:focus {
    border-color: rgba(255, 255, 255, 0.2);
    background: rgba(255, 255, 255, 0.08);
    outline: none;
  }
`;

const UploadArea = styled.div`
  border: 2px dashed rgba(255, 255, 255, 0.2);
  border-radius: 12px;
  padding: 2rem;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s ease;
  margin-bottom: 2rem;

  &:hover {
    border-color: rgba(255, 255, 255, 0.3);
    background: rgba(255, 255, 255, 0.02);
  }

  svg {
    font-size: 2rem;
    color: ${({ theme }) => theme.colors.primary};
    margin-bottom: 1rem;
  }

  h3 {
    font-size: 1.125rem;
    font-weight: 500;
    margin: 0.5rem 0;
    color: ${({ theme }) => theme.colors.text};
  }

  p {
    font-size: 0.875rem;
    color: ${({ theme }) => theme.colors.textLight};
    margin: 0;
  }
`;

const SubmitButton = styled.button`
  width: 100%;
  padding: 1rem;
  background: ${({ theme }) => theme.colors.primary};
  color: white;
  border: none;
  border-radius: 12px;
  font-size: 1rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  margin-top: 2rem;

  &:hover {
    opacity: 0.95;
    transform: translateY(-1px);
  }

  &:disabled {
    opacity: 0.7;
    cursor: not-allowed;
    transform: none;
  }
`;

const ErrorMessage = styled.div`
  color: ${({ theme }) => theme.colors.danger};
  margin-top: 1rem;
  font-size: 0.9rem;
  text-align: center;
`;

const DateInput = styled.input`
  width: 100%;
  padding: 0.75rem;
  font-size: 0.9375rem;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  color: ${({ theme }) => theme.colors.text};
  cursor: pointer;
  transition: all 0.2s ease;

  &::-webkit-calendar-picker-indicator {
    filter: invert(1);
    opacity: 0.6;
    cursor: pointer;
  }

  &:hover,
  &:focus {
    border-color: rgba(255, 255, 255, 0.2);
    background: rgba(255, 255, 255, 0.08);
    outline: none;
  }
`;

const SelectedFileContainer = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: rgba(255, 255, 255, 0.05);
  padding: 0.75rem 1rem;
  border-radius: 8px;
  margin-top: 1rem;
`;

const FileName = styled.p`
  margin: 0;
  color: ${({ theme }) => theme.colors.text};
  font-size: 0.9375rem;
`;

const RemoveButton = styled.button`
  background: none;
  border: none;
  color: ${({ theme }) => theme.colors.danger};
  cursor: pointer;
  padding: 0.5rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  transition: opacity 0.2s ease;

  &:hover {
    opacity: 0.8;
  }

  svg {
    font-size: 1rem;
  }
`;

const NewJobPage: React.FC = () => {
  const navigate = useNavigate();
  const { jobs, setJobs } = useJobs();
  const [formData, setFormData] = useState({
    company: "",
    position: "",
    notes: "",
    status: JobStatus.PENDING,
    applied_date: "",
  });
  const [resume, setResume] = useState<File | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleInputChange = (
    e: React.ChangeEvent<
      HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
    >
  ) => {
    const { name, value } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setResume(e.target.files[0]);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setError(null);

    try {
      const formDataToSend = new FormData();

      // Convert status to lowercase string if it's not already
      const jobData = {
        ...formData,
        status: (formData.status?.toString() || "pending").toLowerCase(),
        // Only include applied_date if it's not empty
        ...(formData.applied_date && { applied_date: formData.applied_date }),
      };

      // Append each field individually to FormData
      Object.entries(jobData).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== "") {
          formDataToSend.append(key, value.toString());
        }
      });

      if (resume) {
        formDataToSend.append("resume", resume);
      }

      const { data } = await api.post("/api/jobs", formDataToSend, {
        headers: {
          "Content-Type": "multipart/form-data",
        },
      });

      // Update jobs context with the new job
      setJobs([...jobs, data]);

      // Navigate to jobs list with the new job ID
      navigate("/jobs", { state: { newJobId: data.id } });
    } catch (error: any) {
      console.error("Error creating job:", error.response?.data || error);
      let errorMessage = "Failed to create job. Please try again.";

      if (error.response?.data?.detail) {
        // Handle validation errors
        if (Array.isArray(error.response.data.detail)) {
          errorMessage = error.response.data.detail
            .map((err: any) => err.msg)
            .join(", ");
        } else {
          errorMessage = error.response.data.detail;
        }
      }

      setError(errorMessage);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRemoveFile = () => {
    setResume(null);
    // Reset the file input
    const fileInput = document.getElementById("resume") as HTMLInputElement;
    if (fileInput) {
      fileInput.value = "";
    }
  };

  return (
    <PageContainer>
      <CardContainer>
        <CardHeader>
          <FaBriefcase />
          <h2>New Job Application</h2>
        </CardHeader>

        <form onSubmit={handleSubmit}>
          <FormGroup>
            <label htmlFor="company">Company</label>
            <Input
              type="text"
              id="company"
              name="company"
              value={formData.company}
              onChange={handleInputChange}
              required
            />
          </FormGroup>

          <FormGroup>
            <label htmlFor="position">Position</label>
            <Input
              type="text"
              id="position"
              name="position"
              value={formData.position}
              onChange={handleInputChange}
              required
            />
          </FormGroup>

          <FormGroup>
            <label htmlFor="status">Application Status</label>
            <Select
              id="status"
              name="status"
              value={formData.status}
              onChange={handleInputChange}
            >
              {Object.values(JobStatus).map((status) => (
                <option key={status} value={status}>
                  {status.charAt(0).toUpperCase() + status.slice(1)}
                </option>
              ))}
            </Select>
          </FormGroup>

          <FormGroup>
            <label htmlFor="applied_date">Applied Date</label>
            <DateInput
              type="date"
              id="applied_date"
              name="applied_date"
              value={formData.applied_date}
              onChange={handleInputChange}
              max={new Date().toISOString().split("T")[0]}
            />
          </FormGroup>

          <FormGroup>
            <label htmlFor="notes">Notes</label>
            <TextArea
              id="notes"
              name="notes"
              value={formData.notes}
              onChange={handleInputChange}
              placeholder="Add any relevant notes about the position..."
            />
          </FormGroup>

          <SubmitButton type="submit" disabled={isSubmitting}>
            {isSubmitting ? "Creating..." : "Create Job Application"}
          </SubmitButton>

          {error && <ErrorMessage>{error}</ErrorMessage>}
        </form>
      </CardContainer>

      <CardContainer>
        <CardHeader>
          <FaFileAlt />
          <h2>Resume</h2>
        </CardHeader>

        <label htmlFor="resume">
          <UploadArea>
            <FaCloudUploadAlt />
            <h3>Upload Resume</h3>
            <p>Drag and drop your resume here or click to browse</p>
            <p>Supported formats: PDF, DOC, DOCX</p>
          </UploadArea>
        </label>
        <input
          type="file"
          id="resume"
          name="resume"
          onChange={handleFileChange}
          accept=".pdf,.doc,.docx"
          style={{ display: "none" }}
        />

        {resume && (
          <SelectedFileContainer>
            <FileName>{resume.name}</FileName>
            <RemoveButton onClick={handleRemoveFile}>
              <FaTrash />
              Remove
            </RemoveButton>
          </SelectedFileContainer>
        )}
      </CardContainer>
    </PageContainer>
  );
};

export default NewJobPage;
