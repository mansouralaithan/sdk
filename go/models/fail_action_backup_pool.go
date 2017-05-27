package models

// This file was generated by the swagger tool.
// Editing this file might prove futile when you re-run the swagger generate command

import (
	strfmt "github.com/go-openapi/strfmt"

	"github.com/go-openapi/errors"
	"github.com/go-openapi/validate"
)

// FailActionBackupPool fail action backup pool
// swagger:model FailActionBackupPool
type FailActionBackupPool struct {

	// Specifies the UUID of the Pool acting as backup pool. It is a reference to an object of type Pool.
	// Required: true
	BackupPoolRef *string `json:"backup_pool_ref"`
}

// Validate validates this fail action backup pool
func (m *FailActionBackupPool) Validate(formats strfmt.Registry) error {
	var res []error

	if err := m.validateBackupPoolRef(formats); err != nil {
		// prop
		res = append(res, err)
	}

	if len(res) > 0 {
		return errors.CompositeValidationError(res...)
	}
	return nil
}

func (m *FailActionBackupPool) validateBackupPoolRef(formats strfmt.Registry) error {

	if err := validate.Required("backup_pool_ref", "body", m.BackupPoolRef); err != nil {
		return err
	}

	return nil
}
